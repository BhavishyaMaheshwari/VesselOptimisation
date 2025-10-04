"""
Discrete-time simulation engine for logistics operations
Simulates vessel arrivals, berth operations, rake movements, and plant deliveries
"""
import pandas as pd
import numpy as np
from typing import Dict, List, Tuple, Optional
import copy
from utils import CostCalculator

class LogisticsSimulator:
    """Discrete-time simulation of logistics operations"""
    
    def __init__(self, data: Dict[str, pd.DataFrame], time_step_hours: int = 6):
        self.vessels_df = data['vessels']
        self.ports_df = data['ports']
        self.plants_df = data['plants']
        self.rail_costs_df = data['rail_costs']
        
        self.time_step_hours = time_step_hours
        self.rake_capacity_mt = 5000
        
        # Create lookup dictionaries
        self.port_lookup = self.ports_df.set_index('port_id').to_dict('index')
        self.plant_lookup = self.plants_df.set_index('plant_id').to_dict('index')
        self.vessel_lookup = self.vessels_df.set_index('vessel_id').to_dict('index')
        
        # Simulation state
        self.current_time = 0
        self.simulation_log = []
        self.vessel_states = {}
        self.port_states = {}
        self.plant_states = {}
        self.rake_states = {}
        self.cost_components = {
            'demurrage': 0.0,
            'port_handling': 0.0,
            'rail_transport': 0.0
        }
        self.rake_trip_count = 0
        
    def initialize_simulation(self, assignments: List[Dict], simulation_days: int = 30):
        """Initialize simulation state"""
        self.simulation_days = simulation_days
        self.total_time_steps = int(simulation_days * 24 / self.time_step_hours)
        self.cost_components = {
            'demurrage': 0.0,
            'port_handling': 0.0,
            'rail_transport': 0.0
        }
        self.rake_trip_count = 0
        self.assignment_states = {}
        
        # Initialize vessel states
        for _, vessel in self.vessels_df.iterrows():
            self.vessel_states[vessel['vessel_id']] = {
                'status': 'en_route',  # en_route, berthed, unloading, departed
                'eta_time_step': int(vessel['eta_day'] * 24 / self.time_step_hours),
                'berth_time_step': None,
                'departure_time_step': None,
                'cargo_remaining': vessel['cargo_mt'],
                'initial_cargo': vessel['cargo_mt'],
                'port_id': vessel['port_id'],
                'assignments': [],
                'planned_berth_time_step': None,
                'handled_cargo': 0.0,
                'demurrage_cost': 0.0
            }
        
        # Initialize port states
        for _, port in self.ports_df.iterrows():
            self.port_states[port['port_id']] = {
                'vessels_queue': [],
                'current_vessel': None,
                'daily_throughput': 0,
                'rakes_in_use': 0,
                'total_handled': 0
            }
        
        # Initialize plant states
        for _, plant in self.plants_df.iterrows():
            self.plant_states[plant['plant_id']] = {
                'total_received': 0,
                'daily_received': 0,
                'demand_remaining': plant['daily_demand_mt'] * simulation_days,
                'deliveries': []
            }
        
        # Process assignments
        self._process_assignments(assignments)
        
        # Initialize rake tracking
        self._initialize_rakes()
    
    def _process_assignments(self, assignments: List[Dict]):
        """Process optimization assignments into simulation events"""
        for raw_assignment in assignments:
            vessel_id = raw_assignment.get('vessel_id')
            port_id = raw_assignment.get('port_id')
            plant_id = raw_assignment.get('plant_id')
            cargo_mt = raw_assignment.get('cargo_mt', 0.0)
            if not vessel_id or vessel_id not in self.vessel_states or cargo_mt <= 0:
                continue

            vessel_state = self.vessel_states[vessel_id]

            planned_berth_time = raw_assignment.get('planned_berth_time')
            if planned_berth_time is None:
                planned_berth_time = raw_assignment.get('berth_time', raw_assignment.get('time_period'))
            if planned_berth_time is not None:
                planned_berth_time_step = int(float(planned_berth_time) * 24 / self.time_step_hours)
            else:
                planned_berth_time_step = None

            rail_cost_per_mt = self._get_rail_cost(port_id, plant_id)

            assignment_state = {
                'vessel_id': vessel_id,
                'port_id': port_id,
                'plant_id': plant_id,
                'total_cargo': cargo_mt,
                'remaining_cargo': cargo_mt,
                'planned_berth_time_step': planned_berth_time_step,
                'rail_cost_per_mt': rail_cost_per_mt
            }

            vessel_state['assignments'].append(assignment_state)

            # Track planned berth window for demurrage calculations
            if planned_berth_time_step is not None:
                if vessel_state['planned_berth_time_step'] is None:
                    vessel_state['planned_berth_time_step'] = planned_berth_time_step
                else:
                    vessel_state['planned_berth_time_step'] = min(
                        vessel_state['planned_berth_time_step'], planned_berth_time_step
                    )

            # Store for quick lookup by vessel/plant if needed
            assignment_key = (vessel_id, plant_id)
            self.assignment_states.setdefault(assignment_key, []).append(assignment_state)
    
    def _initialize_rakes(self):
        """Initialize rake tracking system"""
        rake_id = 0
        for _, port in self.ports_df.iterrows():
            port_id = port['port_id']
            rakes_available = port['rakes_available_per_day']
            
            for i in range(rakes_available * 2):  # Buffer for multi-day operations
                self.rake_states[f"RAKE_{port_id}_{rake_id}"] = {
                    'status': 'available',  # available, loading, in_transit, unloading
                    'home_port': port_id,
                    'current_location': port_id,
                    'cargo_mt': 0,
                    'destination_plant': None,
                    'arrival_time_step': None,
                    'assignment_id': None
                }
                rake_id += 1
    
    def run_simulation(self, assignments: List[Dict], simulation_days: int = 30) -> Dict:
        """Run the discrete-time simulation"""
        print(f"Running simulation for {simulation_days} days with {self.time_step_hours}h time steps")
        
        self.initialize_simulation(assignments, simulation_days)
        
        # Main simulation loop
        for time_step in range(self.total_time_steps):
            self.current_time = time_step
            current_day = time_step * self.time_step_hours / 24
            
            # Process vessel arrivals
            self._process_vessel_arrivals(time_step)
            
            # Process berth operations
            self._process_berth_operations(time_step)
            
            # Process rake operations
            self._process_rake_operations(time_step)
            
            # Process plant deliveries
            self._process_plant_deliveries(time_step)
            
            # Log state periodically
            if time_step % (24 // self.time_step_hours) == 0:  # Daily logging
                self._log_daily_state(int(current_day))
        
        # Calculate final KPIs
        kpis = self._calculate_final_kpis()
        
        results = {
            'kpis': kpis,
            'simulation_log': self.simulation_log,
            'vessel_states': self.vessel_states,
            'port_states': self.port_states,
            'plant_states': self.plant_states,
            'plant_deliveries': {pid: state['total_received'] for pid, state in self.plant_states.items()},
            'cost_components': {
                'demurrage': self.cost_components.get('demurrage', 0.0),
                'port_handling': self.cost_components.get('port_handling', 0.0),
                'rail_transport': self.cost_components.get('rail_transport', 0.0),
                'total': sum(self.cost_components.values())
            },
            'simulation_days': simulation_days
        }
        
        print(f"Simulation completed - Total cost: ${kpis.get('total_cost', 0):,.2f}")
        return results
    
    def _process_vessel_arrivals(self, time_step: int):
        """Process vessel arrivals at ports"""
        for vessel_id, state in self.vessel_states.items():
            if (state['status'] == 'en_route' and 
                state['eta_time_step'] <= time_step):
                
                # Vessel arrives at port
                port_id = state['port_id']
                self.port_states[port_id]['vessels_queue'].append(vessel_id)
                state['status'] = 'waiting'
                
                self.simulation_log.append({
                    'time_step': time_step,
                    'event': 'vessel_arrival',
                    'vessel_id': vessel_id,
                    'port_id': port_id
                })
    
    def _process_berth_operations(self, time_step: int):
        """Process vessel berthing and unloading operations"""
        for port_id, port_state in self.port_states.items():
            
            # Check if current vessel finished unloading
            if port_state['current_vessel']:
                vessel_id = port_state['current_vessel']
                vessel_state = self.vessel_states[vessel_id]
                
                # Simple unloading: assume 8 hours per 10,000 MT
                unloading_duration = max(1, int(vessel_state['cargo_remaining'] / 10000 * 8 / self.time_step_hours))
                
                if (vessel_state['berth_time_step'] and 
                    time_step >= vessel_state['berth_time_step'] + unloading_duration):
                    
                    # Vessel finished unloading
                    vessel_state['status'] = 'departed'
                    vessel_state['departure_time_step'] = time_step
                    port_state['current_vessel'] = None
                    handled_cargo = vessel_state.get('handled_cargo', 0.0)
                    
                    self.simulation_log.append({
                        'time_step': time_step,
                        'event': 'vessel_departure',
                        'vessel_id': vessel_id,
                        'port_id': port_id,
                        'cargo_handled': vessel_state['cargo_remaining']
                    })
            
            # Berth next vessel if available
            if (not port_state['current_vessel'] and 
                port_state['vessels_queue']):
                
                next_vessel_id = port_state['vessels_queue'].pop(0)
                vessel_state = self.vessel_states[next_vessel_id]
                
                # Check if this is the planned berth time
                planned_berth = vessel_state.get('berth_time_step')
                if not planned_berth or time_step >= planned_berth:
                    
                    port_state['current_vessel'] = next_vessel_id
                    vessel_state['status'] = 'berthed'
                    vessel_state['berth_time_step'] = time_step

                    planned_step = vessel_state.get('planned_berth_time_step')
                    if planned_step is None:
                        planned_step = vessel_state['eta_time_step']

                    delay_steps = max(0, time_step - planned_step)
                    delay_hours = delay_steps * self.time_step_hours
                    vessel_info = self.vessel_lookup[next_vessel_id]
                    delay_days = delay_hours / 24.0
                    demurrage_cost = delay_days * vessel_info['demurrage_rate']
                    vessel_state['demurrage_cost'] = demurrage_cost
                    vessel_state['planned_berth_time_hours'] = planned_step * self.time_step_hours
                    vessel_state['actual_berth_time_hours'] = time_step * self.time_step_hours
                    self.cost_components['demurrage'] += demurrage_cost
                    
                    self.simulation_log.append({
                        'time_step': time_step,
                        'event': 'vessel_berth',
                        'vessel_id': next_vessel_id,
                        'port_id': port_id
                    })
                else:
                    # Put back in queue if not time yet
                    port_state['vessels_queue'].insert(0, next_vessel_id)
    
    def _process_rake_operations(self, time_step: int):
        """Process rake loading, transport, and unloading"""
        
        # Process rake assignments from berthed vessels
        for vessel_id, vessel_state in self.vessel_states.items():
            if (vessel_state['status'] == 'berthed' and 
                vessel_state['assignments'] and
                vessel_state['cargo_remaining'] > 0):
                
                # Try to assign rakes for this vessel's cargo
                for assignment in vessel_state['assignments']:
                    if assignment['vessel_id'] == vessel_id and assignment['remaining_cargo'] > 0:
                        self._assign_rakes_to_vessel(vessel_id, assignment, time_step)
        
        # Update rake states
        for rake_id, rake_state in self.rake_states.items():
            if rake_state['status'] == 'in_transit':
                # Check if rake arrived at destination
                if (rake_state['arrival_time_step'] and 
                    time_step >= rake_state['arrival_time_step']):
                    
                    # Rake arrived at plant
                    rake_state['status'] = 'unloading'
                    rake_state['current_location'] = rake_state['destination_plant']
                    
                    # Schedule return (assume 2 time steps for unloading + return)
                    rake_state['arrival_time_step'] = time_step + 2
                    
            elif rake_state['status'] == 'unloading':
                # Check if unloading finished
                if (rake_state['arrival_time_step'] and 
                    time_step >= rake_state['arrival_time_step']):
                    
                    # Deliver cargo to plant
                    plant_id = rake_state['destination_plant']
                    cargo_delivered = rake_state['cargo_mt']
                    
                    if plant_id in self.plant_states:
                        self.plant_states[plant_id]['total_received'] += cargo_delivered
                        self.plant_states[plant_id]['demand_remaining'] = max(
                            0,
                            self.plant_states[plant_id]['demand_remaining'] - cargo_delivered
                        )
                        self.plant_states[plant_id]['deliveries'].append({
                            'time_step': time_step,
                            'cargo_mt': cargo_delivered,
                            'rake_id': rake_id
                        })
                        self.plant_states[plant_id]['daily_received'] += cargo_delivered
                    self.rake_trip_count += 1
                    
                    # Reset rake
                    rake_state['status'] = 'available'
                    rake_state['current_location'] = rake_state['home_port']
                    rake_state['cargo_mt'] = 0
                    rake_state['destination_plant'] = None
                    rake_state['arrival_time_step'] = None
                    
                    self.simulation_log.append({
                        'time_step': time_step,
                        'event': 'cargo_delivery',
                        'rake_id': rake_id,
                        'plant_id': plant_id,
                        'cargo_mt': cargo_delivered
                    })
    
    def _assign_rakes_to_vessel(self, vessel_id: str, assignment: Dict, time_step: int):
        """Assign available rakes to vessel cargo"""
        vessel_state = self.vessel_states[vessel_id]
        port_id = vessel_state['port_id']
        plant_id = assignment['plant_id']
        port_state = self.port_states.get(port_id, {})

        available_rakes = [
            rake_id for rake_id, rake_state in self.rake_states.items()
            if (rake_state['status'] == 'available' and 
                rake_state['current_location'] == port_id)
        ]

        while (available_rakes and vessel_state['cargo_remaining'] > 0 and 
               assignment['remaining_cargo'] > 0):
            rake_id = available_rakes.pop(0)
            rake_state = self.rake_states[rake_id]

            cargo_to_load = min(
                self.rake_capacity_mt,
                vessel_state['cargo_remaining'],
                assignment['remaining_cargo']
            )

            if cargo_to_load <= 0:
                break

            rake_state['status'] = 'loading'
            rake_state['cargo_mt'] = cargo_to_load
            rake_state['destination_plant'] = plant_id
            rake_state['assignment_id'] = f"{vessel_id}_{plant_id}"

            transit_time = self._get_transit_time(port_id, plant_id)
            rake_state['arrival_time_step'] = time_step + 1 + transit_time
            rake_state['status'] = 'in_transit'

            vessel_state['cargo_remaining'] -= cargo_to_load
            vessel_state['handled_cargo'] += cargo_to_load
            assignment['remaining_cargo'] -= cargo_to_load

            if port_state:
                port_state['total_handled'] += cargo_to_load

            handling_cost = cargo_to_load * self.port_lookup[port_id]['handling_cost_per_mt']
            self.cost_components['port_handling'] += handling_cost

            rail_cost = cargo_to_load * assignment['rail_cost_per_mt']
            self.cost_components['rail_transport'] += rail_cost

            self.simulation_log.append({
                'time_step': time_step,
                'event': 'rake_dispatch',
                'rake_id': rake_id,
                'vessel_id': vessel_id,
                'plant_id': plant_id,
                'cargo_mt': cargo_to_load
            })
    
    def _get_transit_time(self, port_id: str, plant_id: str) -> int:
        """Get transit time between port and plant in time steps"""
        try:
            rail_data = self.rail_costs_df[
                (self.rail_costs_df['port_id'] == port_id) & 
                (self.rail_costs_df['plant_id'] == plant_id)
            ]
            if not rail_data.empty:
                transit_days = rail_data.iloc[0].get('transit_days', 2)
                return int(transit_days * 24 / self.time_step_hours)
        except:
            pass
        
        return int(2 * 24 / self.time_step_hours)  # Default 2 days

    def _get_rail_cost(self, port_id: str, plant_id: str) -> float:
        """Get rail transport cost per MT"""
        try:
            rail_data = self.rail_costs_df[
                (self.rail_costs_df['port_id'] == port_id) &
                (self.rail_costs_df['plant_id'] == plant_id)
            ]
            if not rail_data.empty:
                return float(rail_data.iloc[0].get('cost_per_mt', 0.0))
        except Exception:
            pass
        return float(self.rail_costs_df['cost_per_mt'].mean()) if not self.rail_costs_df.empty else 0.0
    
    def _process_plant_deliveries(self, time_step: int):
        """Process plant deliveries and update demand"""
        # This is handled in rake operations
        pass
    
    def _log_daily_state(self, day: int):
        """Log daily state for monitoring"""
        total_vessels_waiting = sum(
            len(port_state['vessels_queue']) 
            for port_state in self.port_states.values()
        )
        
        total_cargo_delivered = sum(
            plant_state['total_received'] 
            for plant_state in self.plant_states.values()
        )
        
        self.simulation_log.append({
            'time_step': self.current_time,
            'event': 'daily_summary',
            'day': day,
            'vessels_waiting': total_vessels_waiting,
            'total_cargo_delivered': total_cargo_delivered
        })

        # Reset daily counters
        for plant_state in self.plant_states.values():
            plant_state['daily_received'] = 0
    
    def _calculate_final_kpis(self) -> Dict[str, float]:
        """Calculate final simulation KPIs"""
        kpis = {}
        
        total_demurrage = self.cost_components.get('demurrage', 0.0)
        total_port_handling = self.cost_components.get('port_handling', 0.0)
        total_rail_transport = self.cost_components.get('rail_transport', 0.0)

        kpis['demurrage_cost'] = total_demurrage
        kpis['port_handling_cost'] = total_port_handling
        kpis['rail_transport_cost'] = total_rail_transport
        kpis['total_cost'] = total_demurrage + total_port_handling + total_rail_transport
        
        # Operational KPIs
        total_demand = sum(plant['daily_demand_mt'] * self.simulation_days for plant in self.plants_df.to_dict('records'))
        total_delivered = sum(plant_state['total_received'] for plant_state in self.plant_states.values())
        
        kpis['demand_fulfillment_pct'] = (total_delivered / total_demand * 100) if total_demand > 0 else 0
        kpis['total_cargo_delivered'] = total_delivered
        kpis['total_demand'] = total_demand
        
        # Vessel performance
        departed_vessels = sum(1 for state in self.vessel_states.values() if state['status'] == 'departed')
        total_vessels = len(self.vessel_states)
        kpis['vessels_processed_pct'] = (departed_vessels / total_vessels * 100) if total_vessels > 0 else 0
        
        # Average waiting time
        total_wait_time = 0
        vessels_with_wait = 0
        for vessel_state in self.vessel_states.values():
            if vessel_state['berth_time_step'] is not None and vessel_state['eta_time_step'] is not None:
                wait_time = max(0, vessel_state['berth_time_step'] - vessel_state['eta_time_step'])
                total_wait_time += wait_time * self.time_step_hours
                vessels_with_wait += 1
        
        kpis['avg_vessel_wait_hours'] = (total_wait_time / vessels_with_wait) if vessels_with_wait > 0 else 0
        
        # Rake utilization
        total_rakes = len(self.rake_states)
        theoretical_capacity = sum(
            self.port_lookup[p].get('rakes_available_per_day', 0) for p in self.port_lookup
        ) * self.simulation_days
        if theoretical_capacity > 0:
            kpis['avg_rake_utilization'] = self.rake_trip_count / theoretical_capacity
        elif total_rakes > 0:
            kpis['avg_rake_utilization'] = self.rake_trip_count / total_rakes
        else:
            kpis['avg_rake_utilization'] = 0
        
        return kpis
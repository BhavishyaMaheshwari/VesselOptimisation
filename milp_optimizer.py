"""
MILP Optimizer using PuLP for exact optimization of rake dispatch
Minimizes total cost: port handling + rail transport + demurrage
"""
import pulp
import pandas as pd
import numpy as np
from typing import Dict, List, Tuple, Optional
from utils import CostCalculator, ETAPredictor
import time
import math

class MILPOptimizer:
    """Mixed Integer Linear Programming optimizer for logistics dispatch"""
    
    def __init__(self, data: Dict[str, pd.DataFrame], time_horizon_days: int = 30):
        self.vessels_df = data['vessels']
        self.ports_df = data['ports'] 
        self.plants_df = data['plants']
        self.rail_costs_df = data['rail_costs']
        self.time_horizon = time_horizon_days
        self.rake_capacity_mt = 5000  # Standard rake capacity
        
        # Create lookup dictionaries for faster access
        self.port_lookup = self.ports_df.set_index('port_id').to_dict('index')
        self.plant_lookup = self.plants_df.set_index('plant_id').to_dict('index')
        self.vessel_lookup = self.vessels_df.set_index('vessel_id').to_dict('index')

        # Predict inherent pre-berthing delays for realism (in days)
        self.eta_predictor = ETAPredictor()
        self.predicted_delay_days: Dict[str, float] = {}
        for vessel_id, vessel_data in self.vessel_lookup.items():
            try:
                delay_hours = self.eta_predictor.predict_delay(
                    vessel_id=vessel_id,
                    port_id=vessel_data['port_id'],
                    base_eta=float(vessel_data['eta_day'])
                )
                self.predicted_delay_days[vessel_id] = max(0.0, delay_hours / 24.0)
            except Exception:
                self.predicted_delay_days[vessel_id] = 0.0
        
    def build_milp_model(self, solver_time_limit: int = 300) -> Tuple[pulp.LpProblem, Dict]:
        """Build the MILP model for rake dispatch optimization"""
        
        print("Building MILP model...")
        
        # Create the optimization problem
        prob = pulp.LpProblem("Rake_Dispatch_Optimization", pulp.LpMinimize)
        
        # Sets
        vessels = self.vessels_df['vessel_id'].tolist()
        ports = self.ports_df['port_id'].tolist()
        plants = self.plants_df['plant_id'].tolist()
        time_periods = list(range(1, self.time_horizon + 1))
        
        # Decision Variables
        # x[v,p,pl,t] = amount of cargo (MT) from vessel v at port p to plant pl in period t
        x = pulp.LpVariable.dicts("cargo_flow",
                                 [(v, p, pl, t) for v in vessels for p in ports 
                                  for pl in plants for t in time_periods],
                                 lowBound=0, cat='Continuous')
        
        # y[v,p,t] = 1 if vessel v berths at port p in period t
        y = pulp.LpVariable.dicts("vessel_berth",
                                 [(v, p, t) for v in vessels for p in ports for t in time_periods],
                                 cat='Binary')
        
        # z[p,pl,t] = number of rakes from port p to plant pl in period t
        z = pulp.LpVariable.dicts("rake_assignment",
                                 [(p, pl, t) for p in ports for pl in plants for t in time_periods],
                                 lowBound=0, cat='Integer')
        
        # Auxiliary variables for costs
        demurrage_cost = pulp.LpVariable.dicts("demurrage", vessels, lowBound=0)
        
        # Objective Function: Minimize total cost
        port_handling_cost = pulp.lpSum([
            x[v, p, pl, t] * self.port_lookup[p]['handling_cost_per_mt']
            for v in vessels for p in ports for pl in plants for t in time_periods
        ])
        
        rail_transport_cost = pulp.lpSum([
            x[v, p, pl, t] * self._get_rail_cost(p, pl)
            for v in vessels for p in ports for pl in plants for t in time_periods
        ])
        
        total_demurrage = pulp.lpSum([demurrage_cost[v] for v in vessels])
        
        prob += port_handling_cost + rail_transport_cost + total_demurrage
        
        # Constraints
        
        # 1. Vessel cargo capacity constraint
        for v in vessels:
            vessel_cargo = self.vessel_lookup[v]['cargo_mt']
            prob += pulp.lpSum([x[v, p, pl, t] for p in ports for pl in plants 
                               for t in time_periods]) == vessel_cargo
        
        # 2. Vessel can only berth at its designated port
        for v in vessels:
            vessel_port = self.vessel_lookup[v]['port_id']
            for p in ports:
                if p != vessel_port:
                    for t in time_periods:
                        prob += y[v, p, t] == 0
        
        # 3. Vessel can berth only after ETA
        for v in vessels:
            vessel_eta = float(self.vessel_lookup[v]['eta_day'])
            vessel_port = self.vessel_lookup[v]['port_id']
            for t in time_periods:
                if t < vessel_eta:
                    prob += y[v, vessel_port, t] == 0
        
        # 4. Vessel berths at most once
        for v in vessels:
            vessel_port = self.vessel_lookup[v]['port_id']
            prob += pulp.lpSum([y[v, vessel_port, t] for t in time_periods]) <= 1
        
        # 5. Cargo flow only when vessel berths
        for v in vessels:
            vessel_port = self.vessel_lookup[v]['port_id']
            vessel_cargo = self.vessel_lookup[v]['cargo_mt']
            for pl in plants:
                for t in time_periods:
                    prob += x[v, vessel_port, pl, t] <= vessel_cargo * y[v, vessel_port, t]

        # 5b. Block cargo flows from non-designated ports entirely
        for v in vessels:
            vessel_port = self.vessel_lookup[v]['port_id']
            for p in ports:
                if p == vessel_port:
                    continue
                for pl in plants:
                    for t in time_periods:
                        prob += x[v, p, pl, t] == 0
        
        # 6. Port capacity constraints
        for p in ports:
            port_capacity = self.port_lookup[p]['daily_capacity_mt']
            for t in time_periods:
                prob += pulp.lpSum([x[v, p, pl, t] for v in vessels for pl in plants]) <= port_capacity
        
        # 7. Rake capacity constraints
        for p in ports:
            for pl in plants:
                for t in time_periods:
                    prob += pulp.lpSum([x[v, p, pl, t] for v in vessels]) <= z[p, pl, t] * self.rake_capacity_mt
        
        # 8. Rake availability constraints
        for p in ports:
            rakes_available = self.port_lookup[p]['rakes_available_per_day']
            for t in time_periods:
                prob += pulp.lpSum([z[p, pl, t] for pl in plants]) <= rakes_available
        
        # 9. Plant demand constraints (soft constraint with penalty)
        # This is handled in post-processing for simplicity
        
        # 10. Demurrage cost calculation (simplified)
        for v in vessels:
            vessel_eta = float(self.vessel_lookup[v]['eta_day'])
            vessel_port = self.vessel_lookup[v]['port_id']
            demurrage_rate = float(self.vessel_lookup[v]['demurrage_rate'])
            inherent_delay = self.predicted_delay_days.get(v, 0.0)

            delay_terms = []
            for t in time_periods:
                effective_delay = max(0.0, (t + inherent_delay) - vessel_eta)
                if effective_delay > 0:
                    delay_terms.append(demurrage_rate * effective_delay * y[v, vessel_port, t])

            if delay_terms:
                prob += demurrage_cost[v] >= pulp.lpSum(delay_terms)
            else:
                prob += demurrage_cost[v] >= 0
        
        variables = {
            'cargo_flow': x,
            'vessel_berth': y, 
            'rake_assignment': z,
            'demurrage_cost': demurrage_cost
        }
        
        return prob, variables
    
    def solve_milp(self, solver_name: str = 'CBC', time_limit: int = 300) -> Dict:
        """Solve the MILP model and return results"""
        
        start_time = time.time()
        
        try:
            prob, variables = self.build_milp_model(time_limit)
            
            # Set solver
            if solver_name.upper() == 'CBC':
                solver = pulp.PULP_CBC_CMD(timeLimit=time_limit, msg=1)
            elif solver_name.upper() == 'GUROBI':
                try:
                    solver = pulp.GUROBI_CMD(timeLimit=time_limit, msg=1)
                except:
                    print("Gurobi not available, falling back to CBC")
                    solver = pulp.PULP_CBC_CMD(timeLimit=time_limit, msg=1)
            else:
                solver = pulp.PULP_CBC_CMD(timeLimit=time_limit, msg=1)
            
            # Solve
            prob.solve(solver)
            
            solve_time = time.time() - start_time
            
            # Extract results
            status = pulp.LpStatus[prob.status]
            objective_value = pulp.value(prob.objective) if prob.status == pulp.LpStatusOptimal else None
            
            assignments = []
            if prob.status == pulp.LpStatusOptimal:
                assignments = self._extract_assignments(variables)
            
            results = {
                'status': status,
                'objective_value': objective_value,
                'solve_time': solve_time,
                'assignments': assignments,
                'solver_used': solver_name,
                'variables_count': prob.numVariables(),
                'constraints_count': prob.numConstraints()
            }
            
            print(f"MILP solved in {solve_time:.2f}s - Status: {status}")
            if objective_value:
                print(f"Objective value: ${objective_value:,.2f}")
            
            return results
            
        except Exception as e:
            print(f"MILP solver error: {e}")
            return {
                'status': 'Error',
                'error': str(e),
                'solve_time': time.time() - start_time,
                'assignments': []
            }
    
    def _get_rail_cost(self, port_id: str, plant_id: str) -> float:
        """Get rail transport cost between port and plant"""
        try:
            cost_row = self.rail_costs_df[
                (self.rail_costs_df['port_id'] == port_id) & 
                (self.rail_costs_df['plant_id'] == plant_id)
            ]
            return cost_row.iloc[0]['cost_per_mt'] if not cost_row.empty else 100.0
        except:
            return 100.0  # Default cost
    
    def _extract_assignments(self, variables: Dict) -> List[Dict]:
        """Extract assignment solution from MILP variables"""
        assignments = []
        
        cargo_flow = variables['cargo_flow']
        vessel_berth = variables['vessel_berth']
        
        for v in self.vessels_df['vessel_id']:
            for p in self.ports_df['port_id']:
                for pl in self.plants_df['plant_id']:
                    for t in range(1, self.time_horizon + 1):
                        cargo_amount = pulp.value(cargo_flow[v, p, pl, t])
                        if cargo_amount is None or cargo_amount <= 0.1:
                            continue

                        cargo_amount = float(cargo_amount)

                        # Check if vessel actually berths in this period
                        berth_status = pulp.value(vessel_berth[v, p, t])
                        if berth_status is None or berth_status < 0.5:
                            continue

                        scheduled_day = int(t)
                        predicted_delay = float(self.predicted_delay_days.get(v, 0.0))
                        planned_eta = float(self.vessel_lookup[v]['eta_day'])
                        actual_berth_time = float(scheduled_day + predicted_delay)

                        assignment = {
                            'vessel_id': v,
                            'port_id': p,
                            'plant_id': pl,
                            'time_period': scheduled_day,
                            'scheduled_day': scheduled_day,
                            'cargo_mt': round(cargo_amount, 2),
                            'berth_time': actual_berth_time,
                            'actual_berth_time': actual_berth_time,
                            'planned_berth_time': planned_eta,
                            'predicted_delay_days': predicted_delay,
                            'rakes_required': int(math.ceil(cargo_amount / self.rake_capacity_mt)),
                            'eta_day': planned_eta
                        }
                        assignments.append(assignment)
        
        return assignments
    
    def create_baseline_solution(self) -> Dict:
        """Create a simple FCFS (First Come First Served) baseline solution"""
        print("Creating FCFS baseline solution...")
        
        assignments = []
        port_utilization: Dict[str, float] = {}  # Track when each port is busy
        
        # Sort vessels by ETA
        vessels_sorted = self.vessels_df.sort_values('eta_day')
        
        # Simple assignment: each vessel to closest plant with matching requirements
        for _, vessel in vessels_sorted.iterrows():
            vessel_port = vessel['port_id']
            cargo_grade = vessel['cargo_grade']
            cargo_mt = vessel['cargo_mt']
            eta = float(vessel['eta_day'])
            predicted_delay = self.predicted_delay_days.get(vessel['vessel_id'], 0.0)
            
            # Find plants that can accept this cargo type
            compatible_plants = self.plants_df[
                self.plants_df['quality_requirements'] == cargo_grade
            ]
            
            if not compatible_plants.empty:
                # Choose plant with highest demand (baseline doesn't optimize)
                target_plant = compatible_plants.loc[compatible_plants['daily_demand_mt'].idxmax()]
                
                # Baseline: vessels may have to wait if port is busy (sequential berthing)
                # This creates realistic delays and demurrage costs
                if vessel_port not in port_utilization:
                    port_utilization[vessel_port] = eta

                arrival_with_delay = eta + predicted_delay
                available_time = port_utilization[vessel_port]
                actual_berth_time = max(arrival_with_delay, available_time)
                
                # Assume port takes 1-2 days to handle cargo (baseline is slower)
                port_handling_days = 1.5  # Baseline is less efficient
                port_utilization[vessel_port] = actual_berth_time + port_handling_days

                scheduled_day = int(math.ceil(actual_berth_time))
                
                assignment = {
                    'vessel_id': vessel['vessel_id'],
                    'port_id': vessel_port,
                    'plant_id': target_plant['plant_id'],
                    'time_period': scheduled_day,
                    'scheduled_day': scheduled_day,
                    'cargo_mt': cargo_mt,
                    'berth_time': actual_berth_time,
                    'actual_berth_time': actual_berth_time,
                    'planned_berth_time': eta,
                    'predicted_delay_days': predicted_delay,
                    'rakes_required': int(np.ceil(cargo_mt / self.rake_capacity_mt))
                }
                assignments.append(assignment)
        
        # Calculate baseline costs (now includes demurrage from delays)
        baseline_cost = self._calculate_assignment_cost(assignments)
        
        print(f"Baseline FCFS cost: ${baseline_cost:,.2f}")
        
        return {
            'status': 'Baseline_FCFS',
            'objective_value': baseline_cost,
            'assignments': assignments,
            'solve_time': 0.1,
            'method': 'First Come First Served (No Optimization)'
        }
    
    def _calculate_assignment_cost(self, assignments: List[Dict]) -> float:
        """Calculate total cost for a set of assignments"""
        total_cost = 0.0
        
        for assignment in assignments:
            port_id = assignment['port_id']
            plant_id = assignment['plant_id']
            cargo_mt = assignment['cargo_mt']
            vessel_id = assignment['vessel_id']
            berth_time = assignment.get('actual_berth_time')
            if berth_time is None:
                berth_time = assignment.get('berth_time', assignment.get('time_period', 0))
            
            # Port handling cost
            port_cost = self.port_lookup[port_id]['handling_cost_per_mt'] * cargo_mt
            
            # Rail transport cost
            rail_cost = self._get_rail_cost(port_id, plant_id) * cargo_mt
            
            # Demurrage cost (critical for realistic baseline)
            vessel_info = self.vessel_lookup[vessel_id]
            vessel_eta = float(assignment.get('planned_berth_time', vessel_info['eta_day']))
            demurrage_rate = vessel_info['demurrage_rate']
            
            # Calculate delay in days (berth time - planned ETA)
            delay_days = max(0, float(berth_time) - vessel_eta) if berth_time is not None else 0
            demurrage_cost = delay_days * demurrage_rate
            
            total_cost += port_cost + rail_cost + demurrage_cost
        
        return total_cost
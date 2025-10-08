"""
Heuristic optimization algorithms: Genetic Algorithm and Simulated Annealing
Refines MILP solutions and provides scalable optimization for large problems
"""
import random
import numpy as np
import pandas as pd
from typing import Dict, List, Tuple, Optional
from deap import base, creator, tools, algorithms
import copy
import time
import math
import re

from utils import ETAPredictor
from seed_utils import get_current_seed

class HeuristicOptimizer:
    """Heuristic optimization using GA and Simulated Annealing"""
    
    def __init__(self, data: Dict[str, pd.DataFrame]):
        self.vessels_df = data['vessels']
        self.ports_df = data['ports']
        self.plants_df = data['plants'] 
        self.rail_costs_df = data['rail_costs']
        self.rake_capacity_mt = 5000
        
        # Create lookup dictionaries
        self.port_lookup = self.ports_df.set_index('port_id').to_dict('index')
        self.plant_lookup = self.plants_df.set_index('plant_id').to_dict('index')
        self.vessel_lookup = self.vessels_df.set_index('vessel_id').to_dict('index')
        
        # DEAP setup will be done when needed
        self.toolbox = None

        self.secondary_port_penalty_per_mt = 50.0
        self.vessel_allowed_ports: Dict[str, List[str]] = {}
        self.primary_port_map: Dict[str, str] = {}

        for vessel_id, vessel_data in self.vessel_lookup.items():
            primary_port = str(vessel_data['port_id']).strip()
            allowed_ports = self._parse_allowed_ports(vessel_data, primary_port)
            self.vessel_allowed_ports[vessel_id] = allowed_ports
            self.primary_port_map[vessel_id] = primary_port

        # Pre-compute predicted delays for each vessel (in days)
        self.eta_predictor = ETAPredictor()
        self.predicted_delay_days: Dict[str, Dict[str, float]] = {}
        for vessel_id, vessel_data in self.vessel_lookup.items():
            eta_day = float(vessel_data['eta_day'])
            delay_map: Dict[str, float] = {}
            for port_id in self.vessel_allowed_ports[vessel_id]:
                try:
                    delay_hours = self.eta_predictor.predict_delay(
                        vessel_id=vessel_id,
                        port_id=port_id,
                        base_eta=eta_day
                    )
                    delay_map[port_id] = max(0.0, delay_hours / 24.0)
                except Exception:
                    delay_map[port_id] = 0.0
            self.predicted_delay_days[vessel_id] = delay_map
    
    def _parse_allowed_ports(self, vessel_row: Dict, primary_port: str) -> List[str]:
        allowed = [primary_port]
        secondary_value = vessel_row.get('secondary_port_id')
        if secondary_value is None:
            return allowed

        if isinstance(secondary_value, (float, int)) and pd.isna(secondary_value):
            return allowed

        if isinstance(secondary_value, str):
            tokens = [tok.strip().upper() for tok in re.split(r'[|;,]+', secondary_value) if tok.strip()]
        elif isinstance(secondary_value, (list, tuple, set)):
            tokens = [str(tok).strip().upper() for tok in secondary_value if str(tok).strip()]
        else:
            tokens = [str(secondary_value).strip().upper()]

        for token in tokens:
            if token and token not in allowed and token in self.port_lookup:
                allowed.append(token)
        return allowed

    def _setup_deap(self):
        """Setup DEAP framework for genetic algorithm"""
        # Clear any existing creators
        try:
            if hasattr(creator, "FitnessMin"):
                del creator.FitnessMin
            if hasattr(creator, "Individual"):
                del creator.Individual
        except:
            pass
            
        try:
            creator.create("FitnessMin", base.Fitness, weights=(-1.0,))
            creator.create("Individual", list, fitness=creator.FitnessMin)
        except Exception as e:
            print(f"DEAP setup warning: {e}")
            # Create fallback classes
            class FitnessMin:
                def __init__(self):
                    self.values = (float('inf'),)
            
            class Individual(list):
                def __init__(self, *args):
                    super().__init__(*args)
                    self.fitness = FitnessMin()
            
            creator.FitnessMin = FitnessMin
            creator.Individual = Individual
        
        self.toolbox = base.Toolbox()
        
    # Individual representation: list of (vessel_id, port_id, plant_id, berth_day)
        self.toolbox.register("individual", self._create_individual)
        self.toolbox.register("population", tools.initRepeat, list, self.toolbox.individual)
        self.toolbox.register("evaluate", self._evaluate_individual)
        self.toolbox.register("mate", self._crossover)
        self.toolbox.register("mutate", self._mutate)
        self.toolbox.register("select", tools.selTournament, tournsize=3)
    
    def _create_individual(self):
        """Create a random individual for GA"""
        individual = []
        
        for _, vessel in self.vessels_df.iterrows():
            vessel_id = vessel['vessel_id']
            cargo_grade = vessel['cargo_grade']
            eta_day = float(vessel['eta_day'])

            allowed_ports = self.vessel_allowed_ports.get(vessel_id, [vessel['port_id']])
            if not allowed_ports:
                continue

            # Find compatible plants
            compatible_plants = self.plants_df[
                self.plants_df['quality_requirements'] == cargo_grade
            ]['plant_id'].tolist()
            
            if compatible_plants:
                plant_id = random.choice(compatible_plants)
                port_id = allowed_ports[0]
                if len(allowed_ports) > 1 and random.random() < 0.15:
                    port_id = random.choice(allowed_ports)
                # Berth day can be ETA or later (up to 7 days delay)
                berth_day = eta_day + random.uniform(0, 7)
                individual.append((vessel_id, port_id, plant_id, berth_day))
        
        return creator.Individual(individual)
    
    def _evaluate_individual(self, individual) -> Tuple[float]:
        """Evaluate fitness of an individual (total cost)"""
        assignments = self._individual_to_assignments(individual)
        total_cost = self._calculate_total_cost(assignments)
        return (total_cost,)
    
    def _individual_to_assignments(self, individual) -> List[Dict]:
        """Convert GA individual to assignment format"""
        assignments = []
        
        for vessel_id, port_id, plant_id, berth_day in individual:
            vessel_data = self.vessel_lookup[vessel_id]
            allowed_ports = self.vessel_allowed_ports.get(vessel_id, [vessel_data['port_id']])
            if not allowed_ports:
                continue
            if port_id not in allowed_ports:
                port_id = allowed_ports[0]

            # Safe handling of berth_day (can be None in hybrid methods)
            if berth_day is None:
                safe_berth_day = float(vessel_data.get('eta_day', 0))
            else:
                safe_berth_day = float(berth_day)

            scheduled_day = safe_berth_day
            predicted_delay = self.predicted_delay_days.get(vessel_id, {}).get(port_id, 0.0)
            actual_berth_time = scheduled_day + predicted_delay
            planned_eta = float(vessel_data.get('eta_day', scheduled_day))

            assignment = {
                'vessel_id': vessel_id,
                'port_id': port_id,
                'plant_id': plant_id,
                'time_period': int(math.ceil(scheduled_day)),
                'scheduled_day': scheduled_day,
                'cargo_mt': vessel_data['cargo_mt'],
                'berth_time': actual_berth_time,
                'actual_berth_time': actual_berth_time,
                'planned_berth_time': planned_eta,
                'predicted_delay_days': predicted_delay,
                'rakes_required': int(np.ceil(vessel_data['cargo_mt'] / self.rake_capacity_mt))
            }
            assignments.append(assignment)
        
        return assignments
    
    def _calculate_total_cost(self, assignments: List[Dict]) -> float:
        """Calculate total cost for assignments"""
        total_cost = 0.0
        
        for assignment in assignments:
            port_id = assignment.get('port_id')
            plant_id = assignment['plant_id']
            cargo_mt = assignment['cargo_mt']
            vessel_id = assignment['vessel_id']
            berth_time = assignment.get('actual_berth_time', assignment.get('berth_time'))

            # Ensure port is valid
            port_info = self.port_lookup.get(port_id)
            if port_info is None:
                fallback_port = self.primary_port_map.get(vessel_id)
                if fallback_port:
                    port_info = self.port_lookup.get(fallback_port)
                    if port_info is not None:
                        port_id = fallback_port
                        assignment['port_id'] = port_id
            if port_info is None:
                # Skip if no usable port info
                continue
            
            # Port handling cost
            port_cost = port_info['handling_cost_per_mt'] * cargo_mt

            # Add secondary port penalty
            primary_port = self.primary_port_map.get(vessel_id, port_id)
            if port_id != primary_port:
                port_cost += cargo_mt * self.secondary_port_penalty_per_mt
            
            # Rail transport cost
            rail_cost = self._get_rail_cost(port_id, plant_id) * cargo_mt
            
            # Demurrage cost
            vessel_eta = assignment.get('planned_berth_time', self.vessel_lookup[vessel_id]['eta_day'])
            delay_days = max(0, float(berth_time) - float(vessel_eta)) if berth_time is not None else 0
            demurrage_rate = self.vessel_lookup[vessel_id]['demurrage_rate']
            demurrage_cost = delay_days * demurrage_rate
            
            total_cost += port_cost + rail_cost + demurrage_cost
        
        # Add penalty for constraint violations
        penalty = self._calculate_constraint_penalties(assignments)
        total_cost += penalty
        
        return total_cost
    
    def _get_rail_cost(self, port_id: str, plant_id: str) -> float:
        """Get rail transport cost between port and plant"""
        try:
            cost_row = self.rail_costs_df[
                (self.rail_costs_df['port_id'] == port_id) & 
                (self.rail_costs_df['plant_id'] == plant_id)
            ]
            return cost_row.iloc[0]['cost_per_mt'] if not cost_row.empty else 100.0
        except:
            return 100.0
    
    def _calculate_constraint_penalties(self, assignments: List[Dict]) -> float:
        """Calculate penalty for constraint violations"""
        penalty = 0.0
        
        # Check port capacity constraints
        port_usage = {}
        for assignment in assignments:
            port_id = assignment['port_id']
            time_period = assignment['time_period']
            cargo_mt = assignment['cargo_mt']
            
            key = (port_id, time_period)
            port_usage[key] = port_usage.get(key, 0) + cargo_mt
        
        for (port_id, time_period), usage in port_usage.items():
            capacity = self.port_lookup[port_id]['daily_capacity_mt']
            if usage > capacity:
                penalty += (usage - capacity) * 50  # Penalty per MT over capacity
        
        # Check rake availability constraints
        rake_usage = {}
        for assignment in assignments:
            port_id = assignment['port_id']
            time_period = assignment['time_period']
            rakes_needed = assignment['rakes_required']
            
            key = (port_id, time_period)
            rake_usage[key] = rake_usage.get(key, 0) + rakes_needed
        
        for (port_id, time_period), usage in rake_usage.items():
            available = self.port_lookup[port_id]['rakes_available_per_day']
            if usage > available:
                penalty += (usage - available) * 10000  # High penalty for rake shortage
        
        return penalty
    
    def _crossover(self, ind1, ind2):
        """Crossover operation for GA"""
        if len(ind1) != len(ind2):
            return ind1, ind2
        
        # Two-point crossover
        if len(ind1) > 2:
            point1 = random.randint(1, len(ind1) - 2)
            point2 = random.randint(point1, len(ind1) - 1)
            
            ind1[point1:point2], ind2[point1:point2] = ind2[point1:point2], ind1[point1:point2]
        
        return ind1, ind2
    
    def _mutate(self, individual):
        """Mutation operation for GA"""
        if len(individual) == 0:
            return (individual,)
        
        # Mutate random gene
        idx = random.randint(0, len(individual) - 1)
        vessel_id, port_id, plant_id, berth_day = individual[idx]
        
        # Get vessel info
        vessel_data = self.vessel_lookup[vessel_id]
        cargo_grade = vessel_data['cargo_grade']
        eta_day = vessel_data['eta_day']
        allowed_ports = self.vessel_allowed_ports.get(
            vessel_id,
            [self.primary_port_map.get(vessel_id, port_id) or port_id]
        )
        
        # Mutation type
        mutation_type = random.choice(['plant', 'time', 'port', 'plant_time'])
        
        if mutation_type in ['plant', 'plant_time']:
            # Change plant assignment
            compatible_plants = self.plants_df[
                self.plants_df['quality_requirements'] == cargo_grade
            ]['plant_id'].tolist()
            if compatible_plants:
                plant_id = random.choice(compatible_plants)
        
        if mutation_type == 'port' and allowed_ports:
            other_ports = [p for p in allowed_ports if p != port_id]
            primary_port = self.primary_port_map.get(vessel_id)
            if other_ports:
                if primary_port and random.random() < 0.5:
                    port_id = primary_port
                else:
                    port_id = random.choice(other_ports)
            elif primary_port:
                port_id = primary_port

        if mutation_type in ['time', 'plant_time']:
            # Change berth time
            berth_day = eta_day + random.uniform(0, 10)

        individual[idx] = (vessel_id, port_id, plant_id, berth_day)
        return (individual,)
    
    def run_genetic_algorithm(self, population_size: int = 50, generations: int = 100,
                            seed_solution: Optional[List[Dict]] = None) -> Dict:
        """Run genetic algorithm optimization"""
        print(f"Running Genetic Algorithm (Pop: {population_size}, Gen: {generations})")
        start_time = time.time()
        
        # Setup DEAP when needed
        if self.toolbox is None:
            self._setup_deap()
        
        # Initialize population
        population = self.toolbox.population(n=population_size)
        
        # Seed with existing solution if provided
        if seed_solution:
            seeded_individual = self._assignments_to_individual(seed_solution)
            if seeded_individual:
                population[0] = creator.Individual(seeded_individual)
        
        # Evaluate initial population
        fitnesses = list(map(self.toolbox.evaluate, population))
        for ind, fit in zip(population, fitnesses):
            ind.fitness.values = fit
        
        # Evolution statistics
        stats = tools.Statistics(lambda ind: ind.fitness.values)
        stats.register("avg", np.mean)
        stats.register("min", np.min)
        stats.register("max", np.max)
        
        # Run evolution
        population, logbook = algorithms.eaSimple(
            population, self.toolbox, 
            cxpb=0.7, mutpb=0.2, 
            ngen=generations, 
            stats=stats, 
            verbose=False
        )
        
        # Get best solution
        best_individual = tools.selBest(population, 1)[0]
        best_assignments = self._individual_to_assignments(best_individual)
        
        solve_time = time.time() - start_time
        
        seed_used = get_current_seed()

        result = {
            'status': 'GA_Optimized',
            'objective_value': best_individual.fitness.values[0],
            'assignments': best_assignments,
            'solve_time': solve_time,
            'generations': generations,
            'population_size': population_size,
            'evolution_log': logbook,
            'rng_seed': seed_used
        }
        
        print(f"GA completed in {solve_time:.2f}s - Best cost: ${result['objective_value']:,.2f}")
        return result
    
    def _assignments_to_individual(self, assignments: List[Dict]) -> Optional[List[Tuple]]:
        """Convert assignments to GA individual format"""
        try:
            individual = []
            for assignment in assignments:
                vessel_id = assignment['vessel_id']
                plant_id = assignment['plant_id']
                port_id = assignment.get('port_id')
                if port_id is None:
                    port_id = self.primary_port_map.get(
                        vessel_id,
                        self.vessel_allowed_ports.get(vessel_id, [None])[0]
                    )

                berth_time = assignment.get('berth_time')
                if berth_time is None:
                    berth_time = assignment.get('scheduled_day')
                if berth_time is None:
                    time_period = assignment.get('time_period')
                    if time_period is not None:
                        berth_time = float(time_period)
                    else:
                        berth_time = float(self.vessel_lookup[vessel_id].get('eta_day', 0))

                individual.append((vessel_id, port_id, plant_id, berth_time))
            return individual
        except Exception as e:
            print(f"Error converting assignments to individual: {e}")
            return None
    
    def run_simulated_annealing(self, initial_solution: Dict, 
                              max_iterations: int = 1000,
                              initial_temp: float = 10000.0,
                              cooling_rate: float = 0.95) -> Dict:
        """Run simulated annealing to refine solution"""
        print(f"Running Simulated Annealing ({max_iterations} iterations)")
        start_time = time.time()
        
        # Convert initial solution
        current_assignments = initial_solution['assignments'].copy()
        current_cost = self._calculate_total_cost(current_assignments)
        
        best_assignments = copy.deepcopy(current_assignments)
        best_cost = current_cost
        
        temperature = initial_temp
        
        for iteration in range(max_iterations):
            # Generate neighbor solution
            neighbor_assignments = self._generate_neighbor(current_assignments)
            neighbor_cost = self._calculate_total_cost(neighbor_assignments)
            
            # Accept or reject
            if neighbor_cost < current_cost:
                # Always accept better solution
                current_assignments = neighbor_assignments
                current_cost = neighbor_cost
                
                if current_cost < best_cost:
                    best_assignments = copy.deepcopy(current_assignments)
                    best_cost = current_cost
            else:
                # Accept worse solution with probability
                delta = neighbor_cost - current_cost
                probability = np.exp(-delta / temperature) if temperature > 0 else 0
                
                if random.random() < probability:
                    current_assignments = neighbor_assignments
                    current_cost = neighbor_cost
            
            # Cool down
            temperature *= cooling_rate
            
            # Progress update
            if iteration % 200 == 0:
                print(f"SA Iteration {iteration}: Current={current_cost:.0f}, Best={best_cost:.0f}, Temp={temperature:.1f}")
        
        solve_time = time.time() - start_time
        
        seed_used = get_current_seed()

        result = {
            'status': 'SA_Refined',
            'objective_value': best_cost,
            'assignments': best_assignments,
            'solve_time': solve_time,
            'iterations': max_iterations,
            'initial_cost': initial_solution['objective_value'],
            'improvement': initial_solution['objective_value'] - best_cost,
            'rng_seed': seed_used
        }
        
        print(f"SA completed in {solve_time:.2f}s - Final cost: ${best_cost:,.2f}")
        return result
    
    def _generate_neighbor(self, assignments: List[Dict]) -> List[Dict]:
        """Generate neighbor solution for simulated annealing"""
        neighbor = copy.deepcopy(assignments)
        
        if not neighbor:
            return neighbor
        
        # Random modification
        idx = random.randint(0, len(neighbor) - 1)
        assignment = neighbor[idx]
        
        vessel_id = assignment['vessel_id']
        vessel_data = self.vessel_lookup[vessel_id]
        cargo_grade = vessel_data['cargo_grade']
        eta_day = vessel_data['eta_day']
        
        # Choose modification type
        modification = random.choice(['plant', 'time', 'port'])
        
        if modification == 'plant':
            # Change plant assignment
            compatible_plants = self.plants_df[
                self.plants_df['quality_requirements'] == cargo_grade
            ]['plant_id'].tolist()
            
            if len(compatible_plants) > 1:
                current_plant = assignment['plant_id']
                new_plants = [p for p in compatible_plants if p != current_plant]
                if new_plants:
                    assignment['plant_id'] = random.choice(new_plants)
        
        elif modification == 'port':
            allowed_ports = self.vessel_allowed_ports.get(
                vessel_id,
                [self.primary_port_map.get(vessel_id, assignment['port_id']) or assignment['port_id']]
            )
            if allowed_ports:
                current_port = assignment['port_id']
                alternative_ports = [p for p in allowed_ports if p != current_port]
                primary_port = self.primary_port_map.get(vessel_id)

                chosen_port = current_port
                if alternative_ports:
                    if primary_port and random.random() < 0.5:
                        chosen_port = primary_port
                    else:
                        chosen_port = random.choice(alternative_ports)
                elif primary_port:
                    chosen_port = primary_port

                if chosen_port != current_port:
                    assignment['port_id'] = chosen_port
                    scheduled_day = assignment.get('scheduled_day', assignment.get('time_period', eta_day))
                    if scheduled_day is None:
                        scheduled_day = eta_day
                    new_delay = self.predicted_delay_days.get(vessel_id, {}).get(chosen_port, 0.0)
                    actual_berth = scheduled_day + new_delay
                    assignment['predicted_delay_days'] = new_delay
                    assignment['berth_time'] = actual_berth
                    assignment['actual_berth_time'] = actual_berth
                    assignment['time_period'] = int(math.ceil(scheduled_day))

        elif modification == 'time':
            # Change scheduled berth day (±2 days) respecting ETA
            current_schedule = assignment.get('scheduled_day', assignment.get('time_period', eta_day))
            if current_schedule is None:
                current_schedule = eta_day
            new_schedule = max(eta_day, float(current_schedule) + random.uniform(-2, 2))
            current_port = assignment['port_id']
            predicted_delay = assignment.get(
                'predicted_delay_days',
                self.predicted_delay_days.get(vessel_id, {}).get(current_port, 0.0)
            )
            actual_berth = new_schedule + predicted_delay

            assignment['scheduled_day'] = new_schedule
            assignment['time_period'] = int(math.ceil(new_schedule))
            assignment['berth_time'] = actual_berth
            assignment['actual_berth_time'] = actual_berth
            assignment['predicted_delay_days'] = predicted_delay
            assignment['planned_berth_time'] = assignment.get('planned_berth_time', eta_day)
        
        return neighbor
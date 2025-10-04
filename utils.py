"""
Utility functions for cost calculations, ML stubs, and helper functions
"""
import numpy as np
import pandas as pd
from typing import Dict, List, Tuple, Optional
from sklearn.ensemble import GradientBoostingRegressor
from sklearn.model_selection import train_test_split
import random

class ETAPredictor:
    """ML stub for ETA/delay prediction - placeholder for real ML model"""
    
    def __init__(self):
        self.model = None
        self.is_trained = False
        
    def train_stub_model(self, historical_data: Optional[pd.DataFrame] = None):
        """Train a simple stub model for ETA prediction"""
        # Generate synthetic training data if none provided
        if historical_data is None:
            n_samples = 1000
            X = np.random.rand(n_samples, 4)  # weather, port_congestion, vessel_size, season
            # Synthetic delay pattern: weather + congestion + random noise
            y = (X[:, 0] * 2 + X[:, 1] * 3 + np.random.normal(0, 0.5, n_samples)) * 24  # hours
            y = np.clip(y, 0, 72)  # Max 3 days delay
        else:
            # TODO: Extract features from real historical data
            X = historical_data[['weather_score', 'port_congestion', 'vessel_size', 'season']].values
            y = historical_data['actual_delay_hours'].values
        
        # Train simple gradient boosting model
        self.model = GradientBoostingRegressor(n_estimators=50, random_state=42)
        X_train, X_test, y_train, y_test = train_test_split(X, y, test_size=0.2, random_state=42)
        self.model.fit(X_train, y_train)
        self.is_trained = True
        
        return self.model.score(X_test, y_test)
    
    def predict_delay(self, vessel_id: str, port_id: str, base_eta: float, 
                     weather_score: float = None, port_congestion: float = None) -> float:
        """
        Predict ETA delay for a vessel
        
        Args:
            vessel_id: Vessel identifier
            port_id: Port identifier  
            base_eta: Original ETA in days
            weather_score: Weather conditions (0-1, higher = worse)
            port_congestion: Port congestion level (0-1, higher = more congested)
            
        Returns:
            Predicted delay in hours
        """
        if not self.is_trained:
            self.train_stub_model()
        
        # Use defaults if not provided
        if weather_score is None:
            weather_score = random.uniform(0.1, 0.8)
        if port_congestion is None:
            port_congestion = random.uniform(0.2, 0.7)
        
        # Simple feature engineering
        vessel_size = hash(vessel_id) % 100 / 100.0  # Pseudo vessel size
        season = (base_eta % 365) / 365.0  # Seasonal factor
        
        features = np.array([[weather_score, port_congestion, vessel_size, season]])
        predicted_delay = self.model.predict(features)[0]
        
        return max(0, predicted_delay)  # No negative delays

class CostCalculator:
    """Utility class for various cost calculations"""
    
    @staticmethod
    def calculate_demurrage_cost(vessel_data: pd.Series, actual_berth_time: float, 
                               planned_berth_time: float) -> float:
        """Calculate demurrage cost for vessel delays"""
        if pd.isna(actual_berth_time) or pd.isna(planned_berth_time):
            return 0.0
        delay_hours = max(0, actual_berth_time - planned_berth_time)
        delay_days = delay_hours / 24.0
        return delay_days * vessel_data['demurrage_rate']
    
    @staticmethod
    def calculate_port_handling_cost(cargo_mt: float, port_data: pd.Series) -> float:
        """Calculate port handling costs"""
        return cargo_mt * port_data['handling_cost_per_mt']
    
    @staticmethod
    def calculate_rail_transport_cost(cargo_mt: float, rail_cost_per_mt: float) -> float:
        """Calculate rail transport costs"""
        return cargo_mt * rail_cost_per_mt
    
    @staticmethod
    def calculate_total_logistics_cost(assignments: List[Dict], 
                                     vessels_df: pd.DataFrame,
                                     ports_df: pd.DataFrame,
                                     rail_costs_df: pd.DataFrame) -> Dict[str, float]:
        """Calculate comprehensive logistics costs"""
        costs = {
            'port_handling': 0.0,
            'rail_transport': 0.0,
            'demurrage': 0.0,
            'total': 0.0
        }
        
        for assignment in assignments:
            vessel_id = assignment['vessel_id']
            port_id = assignment['port_id']
            plant_id = assignment['plant_id']
            cargo_mt = assignment['cargo_mt']
            
            # Port handling cost
            port_rows = ports_df[ports_df['port_id'] == port_id]
            if port_rows.empty:
                continue
            port_data = port_rows.iloc[0]
            costs['port_handling'] += CostCalculator.calculate_port_handling_cost(cargo_mt, port_data)
            
            # Rail transport cost
            rail_rows = rail_costs_df[
                (rail_costs_df['port_id'] == port_id) & 
                (rail_costs_df['plant_id'] == plant_id)
            ]
            if rail_rows.empty:
                rail_cost_per_mt = rail_costs_df['cost_per_mt'].mean() if not rail_costs_df.empty else 0.0
            else:
                rail_cost_per_mt = rail_rows.iloc[0]['cost_per_mt']
            costs['rail_transport'] += CostCalculator.calculate_rail_transport_cost(
                cargo_mt, rail_cost_per_mt
            )
            
            # Demurrage cost (if delay information available)
            if 'actual_berth_time' in assignment and 'planned_berth_time' in assignment:
                vessel_data = vessels_df[vessels_df['vessel_id'] == vessel_id].iloc[0]
                costs['demurrage'] += CostCalculator.calculate_demurrage_cost(
                    vessel_data, assignment['actual_berth_time'], assignment['planned_berth_time']
                )
        
        costs['total'] = costs['port_handling'] + costs['rail_transport'] + costs['demurrage']
        return costs

class ScenarioGenerator:
    """Generate what-if scenarios for analysis"""
    
    @staticmethod
    def apply_eta_delays(vessels_df: pd.DataFrame, delay_scenario: str) -> pd.DataFrame:
        """Apply ETA delays based on scenario"""
        vessels_modified = vessels_df.copy()
        
        if delay_scenario == 'P10':  # 10th percentile - minor delays
            delay_multiplier = np.random.uniform(1.0, 1.2, len(vessels_modified))
        elif delay_scenario == 'P50':  # 50th percentile - moderate delays  
            delay_multiplier = np.random.uniform(1.1, 1.5, len(vessels_modified))
        elif delay_scenario == 'P90':  # 90th percentile - severe delays
            delay_multiplier = np.random.uniform(1.3, 2.0, len(vessels_modified))
        else:
            delay_multiplier = np.ones(len(vessels_modified))
        
        vessels_modified['eta_day'] = vessels_modified['eta_day'] * delay_multiplier
        return vessels_modified
    
    @staticmethod
    def reduce_rake_availability(ports_df: pd.DataFrame, reduction_pct: float) -> pd.DataFrame:
        """Reduce rake availability by specified percentage"""
        ports_modified = ports_df.copy()
        ports_modified['rakes_available_per_day'] = (
            ports_modified['rakes_available_per_day'] * (1 - reduction_pct / 100)
        ).astype(int)
        return ports_modified
    
    @staticmethod
    def spike_plant_demand(plants_df: pd.DataFrame, plant_id: str, spike_pct: float) -> pd.DataFrame:
        """Increase demand for specific plant"""
        plants_modified = plants_df.copy()
        mask = plants_modified['plant_id'] == plant_id
        plants_modified.loc[mask, 'daily_demand_mt'] *= (1 + spike_pct / 100)
        return plants_modified

def format_currency(amount: float) -> str:
    """Format currency with appropriate units"""
    if amount >= 1e6:
        return f"${amount/1e6:.1f}M"
    elif amount >= 1e3:
        return f"${amount/1e3:.1f}K"
    else:
        return f"${amount:.0f}"

def format_tonnage(tonnage: float) -> str:
    """Format tonnage with appropriate units"""
    if tonnage >= 1e6:
        return f"{tonnage/1e6:.1f}M MT"
    elif tonnage >= 1e3:
        return f"{tonnage/1e3:.1f}K MT"
    else:
        return f"{tonnage:.0f} MT"

def calculate_kpis(assignments: List[Dict], vessels_df: pd.DataFrame, 
                  plants_df: pd.DataFrame, simulation_results: Dict = None,
                  ports_df: Optional[pd.DataFrame] = None,
                  rail_costs_df: Optional[pd.DataFrame] = None) -> Dict[str, float]:
    """Calculate key performance indicators"""
    kpis: Dict[str, float] = {}

    vessel_lookup = vessels_df.set_index('vessel_id').to_dict('index') if not vessels_df.empty else {}
    port_lookup = ports_df.set_index('port_id').to_dict('index') if ports_df is not None and not ports_df.empty else {}
    plant_lookup = plants_df.set_index('plant_id').to_dict('index') if not plants_df.empty else {}

    if simulation_results:
        # Start with KPIs coming from simulation (already aggregated)
        kpis.update(simulation_results.get('kpis', {}))
        # Include cost component breakdown if available
        if 'cost_components' in simulation_results:
            cost_components = simulation_results['cost_components']
            kpis.setdefault('total_cost', cost_components.get('total', 0.0))
            kpis.setdefault('demurrage_cost', cost_components.get('demurrage', 0.0))
            kpis.setdefault('port_handling_cost', cost_components.get('port_handling', 0.0))
            kpis.setdefault('rail_transport_cost', cost_components.get('rail_transport', 0.0))

    # If we don't have simulation metrics yet, compute cost metrics from assignments
    elif assignments and ports_df is not None and rail_costs_df is not None:
        cost_components = CostCalculator.calculate_total_logistics_cost(
            assignments, vessels_df, ports_df, rail_costs_df
        )
        kpis['total_cost'] = cost_components['total']
        kpis['demurrage_cost'] = cost_components['demurrage']
        kpis['port_handling_cost'] = cost_components['port_handling']
        kpis['rail_transport_cost'] = cost_components['rail_transport']

        # Operational estimates directly from assignments
        total_delivered = sum(a.get('cargo_mt', 0.0) for a in assignments)
        unique_vessels = {a['vessel_id'] for a in assignments if 'vessel_id' in a}
        total_vessels = len(vessels_df)
        horizon_days = max((a.get('time_period') or 1) for a in assignments) if assignments else 1
        horizon_days = max(1, horizon_days)

        # Ensure any fractional berth times are accounted for
        if any(isinstance(a.get('berth_time'), float) and not a.get('time_period') for a in assignments):
            horizon_days = max(
                horizon_days,
                int(max(a.get('berth_time', 0) for a in assignments) + 1)
            )

        total_demand_est = plants_df['daily_demand_mt'].sum() * horizon_days if not plants_df.empty else 0.0
        if total_demand_est > 0:
            kpis['demand_fulfillment_pct'] = (total_delivered / total_demand_est) * 100
        else:
            kpis['demand_fulfillment_pct'] = 0.0

        if total_vessels > 0:
            kpis['vessels_processed_pct'] = (len(unique_vessels) / total_vessels) * 100
        else:
            kpis['vessels_processed_pct'] = 0.0

        # Aggregate per vessel to avoid counting splits multiple times
        per_vessel_wait_days: Dict[str, float] = {}
        for vessel_id in unique_vessels:
            if vessel_id not in vessel_lookup:
                continue
            eta_day = float(vessel_lookup[vessel_id].get('eta_day', 0))
            # Find earliest planned berth across this vessel's assignments
            planned_values = []
            for a in assignments:
                if a.get('vessel_id') != vessel_id:
                    continue
                planned = a.get('planned_berth_time')
                if planned is None:
                    planned = a.get('berth_time')
                if planned is None:
                    planned = a.get('time_period')
                if planned is not None:
                    planned_values.append(float(planned))
            if planned_values:
                min_planned = min(planned_values)
                per_vessel_wait_days[vessel_id] = max(0.0, min_planned - eta_day)
            else:
                per_vessel_wait_days[vessel_id] = 0.0

        waits = [wd for wd in per_vessel_wait_days.values() if wd > 0]
        kpis['avg_vessel_wait_hours'] = (sum(waits) * 24.0 / len(waits)) if waits else 0.0

        # Demurrage based on per-vessel wait and rate
        estimated_demurrage = 0.0
        for vessel_id, wait_days in per_vessel_wait_days.items():
            if wait_days > 0 and vessel_id in vessel_lookup:
                estimated_demurrage += wait_days * float(vessel_lookup[vessel_id].get('demurrage_rate', 0.0))
        if 'demurrage_cost' not in kpis:
            kpis['demurrage_cost'] = estimated_demurrage

        # Estimate rake utilization based on assignments
        total_rakes_required = sum(a.get('rakes_required', 0) for a in assignments)
        if ports_df is not None and not ports_df.empty:
            daily_rake_capacity = ports_df['rakes_available_per_day'].sum()
            theoretical_rake_trips = daily_rake_capacity * horizon_days if daily_rake_capacity else 0
        else:
            theoretical_rake_trips = 0
        if theoretical_rake_trips > 0:
            kpis['avg_rake_utilization'] = total_rakes_required / theoretical_rake_trips
        else:
            daily_rake_capacity = ports_df['rakes_available_per_day'].sum() if ports_df is not None and not ports_df.empty else 0
            kpis['avg_rake_utilization'] = (total_rakes_required / daily_rake_capacity) if daily_rake_capacity else 0.0

    # General cargo statistics
    if assignments:
        total_cargo = sum(a['cargo_mt'] for a in assignments)
        kpis.setdefault('total_cargo_handled', total_cargo)
        kpis.setdefault('avg_cargo_per_assignment', total_cargo / len(assignments))

    # Demand fulfillment from simulation or estimates
    if simulation_results and 'plant_deliveries' in simulation_results:
        plant_deliveries = simulation_results['plant_deliveries']
        total_delivered = sum(plant_deliveries.values())
    elif assignments:
        total_delivered = sum(a['cargo_mt'] for a in assignments)
    else:
        total_delivered = 0.0

    total_demand = plants_df['daily_demand_mt'].sum() if not plants_df.empty else 0.0
    if simulation_results and simulation_results.get('simulation_days'):
        total_demand *= simulation_results['simulation_days']
    elif not simulation_results and assignments:
        # Fall back to estimated horizon used above
        horizon_days = max((a.get('time_period') or 1) for a in assignments)
        horizon_days = max(1, horizon_days)
        total_demand *= horizon_days

    kpis.setdefault('total_demand', total_demand)

    if total_demand > 0:
        kpis.setdefault('demand_fulfillment_pct', (total_delivered / total_demand) * 100)
    else:
        kpis.setdefault('demand_fulfillment_pct', 0.0)

    # Ensure default values exist for UI-friendly KPIs
    kpis.setdefault('avg_vessel_wait_hours', 0.0)
    kpis.setdefault('avg_rake_utilization', 0.0)
    kpis.setdefault('vessels_processed_pct', 0.0)
    kpis.setdefault('demurrage_cost', kpis.get('demurrage_cost', 0.0))
    kpis.setdefault('total_cost', kpis.get('total_cost', 0.0))

    # Normalize numpy numeric types to native Python floats
    try:
        import numpy as np
        numpy_numeric = (np.floating, np.integer)
    except Exception:
        numpy_numeric = tuple()

    for key, value in list(kpis.items()):
        if isinstance(value, numpy_numeric):
            kpis[key] = float(value)

    return kpis
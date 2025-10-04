"""
Data loader and validation for the SIH Logistics Optimization System
Handles toy dataset generation and CSV file uploads with validation
"""
import pandas as pd
import numpy as np
from typing import Dict, List, Tuple, Optional
import io
import base64

class DataLoader:
    """Handles data loading, validation, and toy dataset generation"""
    
    @staticmethod
    def get_toy_dataset() -> Dict[str, pd.DataFrame]:
        """Generate embedded toy dataset for immediate demo"""
        
        # Ports data
        ports_data = {
            'port_id': ['HALDIA', 'PARADIP', 'VIZAG'],
            'port_name': ['Haldia Port', 'Paradip Port', 'Visakhapatnam Port'],
            'handling_cost_per_mt': [25.0, 22.0, 28.0],
            'daily_capacity_mt': [50000, 60000, 55000],
            'rakes_available_per_day': [8, 10, 7]
        }
        
        # Vessels data
        vessels_data = {
            'vessel_id': ['MV_IRON_1', 'MV_COAL_1', 'MV_IRON_2', 'MV_COAL_2', 'MV_IRON_3', 
                         'MV_COAL_3', 'MV_IRON_4', 'MV_COAL_4', 'MV_IRON_5', 'MV_COAL_5'],
            'cargo_mt': [25000, 30000, 22000, 28000, 26000, 32000, 24000, 29000, 27000, 31000],
            'eta_day': [1, 2, 3, 4, 5, 6, 7, 8, 9, 10],
            'port_id': ['HALDIA', 'PARADIP', 'VIZAG', 'HALDIA', 'PARADIP', 
                       'VIZAG', 'HALDIA', 'PARADIP', 'VIZAG', 'HALDIA'],
            'demurrage_rate': [5000, 6000, 4500, 5500, 5200, 6200, 4800, 5800, 5100, 5900],
            'cargo_grade': ['IRON_ORE', 'COAL', 'IRON_ORE', 'COAL', 'IRON_ORE', 
                           'COAL', 'IRON_ORE', 'COAL', 'IRON_ORE', 'COAL']
        }
        
        # Plants data
        plants_data = {
            'plant_id': ['PLANT_A', 'PLANT_B', 'PLANT_C', 'PLANT_D', 'PLANT_E'],
            'plant_name': ['Steel Plant A', 'Steel Plant B', 'Steel Plant C', 'Steel Plant D', 'Steel Plant E'],
            'daily_demand_mt': [8000, 6000, 10000, 12000, 4000],
            'quality_requirements': ['IRON_ORE', 'COAL', 'IRON_ORE', 'COAL', 'IRON_ORE']
        }
        
        # Rail costs data
        rail_costs_data = []
        for port in ports_data['port_id']:
            for plant in plants_data['plant_id']:
                base_cost = np.random.uniform(80, 150)
                rail_costs_data.append({
                    'port_id': port,
                    'plant_id': plant,
                    'cost_per_mt': round(base_cost, 2),
                    'distance_km': int(np.random.uniform(200, 800)),
                    'transit_days': int(np.random.uniform(1, 3))
                })
        
        return {
            'ports': pd.DataFrame(ports_data),
            'vessels': pd.DataFrame(vessels_data),
            'plants': pd.DataFrame(plants_data),
            'rail_costs': pd.DataFrame(rail_costs_data)
        }
    
    @staticmethod
    def validate_csv_data(data: Dict[str, pd.DataFrame]) -> Tuple[bool, List[str]]:
        """Validate uploaded CSV data structure and content"""
        errors = []
        
        # Required columns for each dataset
        required_columns = {
            'ports': ['port_id', 'handling_cost_per_mt', 'daily_capacity_mt', 'rakes_available_per_day'],
            'vessels': ['vessel_id', 'cargo_mt', 'eta_day', 'port_id', 'demurrage_rate', 'cargo_grade'],
            'plants': ['plant_id', 'daily_demand_mt', 'quality_requirements'],
            'rail_costs': ['port_id', 'plant_id', 'cost_per_mt']
        }
        
        # Check if all required datasets are present
        for dataset_name in required_columns.keys():
            if dataset_name not in data:
                errors.append(f"Missing required dataset: {dataset_name}")
                continue
                
            df = data[dataset_name]
            
            # Check required columns
            missing_cols = set(required_columns[dataset_name]) - set(df.columns)
            if missing_cols:
                errors.append(f"{dataset_name}: Missing columns {missing_cols}")
            
            # Check for empty dataframes
            if df.empty:
                errors.append(f"{dataset_name}: Dataset is empty")
            
            # Dataset-specific validations
            if dataset_name == 'vessels':
                if 'cargo_mt' in df.columns and (df['cargo_mt'] <= 0).any():
                    errors.append("vessels: cargo_mt must be positive")
                if 'eta_day' in df.columns and (df['eta_day'] < 0).any():
                    errors.append("vessels: eta_day must be non-negative")
            
            elif dataset_name == 'ports':
                if 'daily_capacity_mt' in df.columns and (df['daily_capacity_mt'] <= 0).any():
                    errors.append("ports: daily_capacity_mt must be positive")
                if 'rakes_available_per_day' in df.columns and (df['rakes_available_per_day'] <= 0).any():
                    errors.append("ports: rakes_available_per_day must be positive")
            
            elif dataset_name == 'plants':
                if 'daily_demand_mt' in df.columns and (df['daily_demand_mt'] <= 0).any():
                    errors.append("plants: daily_demand_mt must be positive")
        
        return len(errors) == 0, errors   
 
    @staticmethod
    def parse_uploaded_file(contents: str, filename: str) -> Optional[pd.DataFrame]:
        """Parse uploaded CSV file content"""
        try:
            content_type, content_string = contents.split(',')
            decoded = base64.b64decode(content_string)
            
            if 'csv' in filename:
                df = pd.read_csv(io.StringIO(decoded.decode('utf-8')))
            elif 'xlsx' in filename or 'xls' in filename:
                df = pd.read_excel(io.BytesIO(decoded))
            else:
                return None
                
            return df
        except Exception as e:
            print(f"Error parsing file {filename}: {e}")
            return None
    
    @staticmethod
    def create_sample_csvs() -> Dict[str, str]:
        """Create sample CSV content for download templates"""
        toy_data = DataLoader.get_toy_dataset()
        
        csv_contents = {}
        for name, df in toy_data.items():
            csv_contents[f"{name}.csv"] = df.to_csv(index=False)
        
        return csv_contents
    
    @staticmethod
    def get_data_summary(data: Dict[str, pd.DataFrame]) -> Dict[str, any]:
        """Generate summary statistics for loaded data"""
        summary = {}
        
        if 'vessels' in data:
            vessels = data['vessels']
            summary['total_vessels'] = len(vessels)
            summary['total_cargo_mt'] = vessels['cargo_mt'].sum()
            summary['avg_eta_days'] = vessels['eta_day'].mean()
            summary['cargo_types'] = vessels['cargo_grade'].unique().tolist()
        
        if 'ports' in data:
            ports = data['ports']
            summary['total_ports'] = len(ports)
            summary['total_port_capacity'] = ports['daily_capacity_mt'].sum()
            summary['total_rakes_available'] = ports['rakes_available_per_day'].sum()
        
        if 'plants' in data:
            plants = data['plants']
            summary['total_plants'] = len(plants)
            summary['total_demand_mt'] = plants['daily_demand_mt'].sum()
        
        return summary
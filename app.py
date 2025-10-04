"""
Main Dash application for SIH Logistics Optimization Simulator
Production-quality web interface with interactive optimization and visualization
"""
import dash
from dash import dcc, html, Input, Output, State, callback_context, dash_table
import dash_bootstrap_components as dbc
import dash_daq as daq
import plotly.graph_objects as go
from plotly.subplots import make_subplots
import pandas as pd
import numpy as np
import json
import time
import io
import zipfile
from typing import Dict, List, Optional

# Import our modules
from data_loader import DataLoader
from milp_optimizer import MILPOptimizer
from heuristics import HeuristicOptimizer
from simulation import LogisticsSimulator
from visuals import LogisticsVisualizer
from utils import ETAPredictor, ScenarioGenerator, calculate_kpis, format_currency

# Initialize Dash app
app = dash.Dash(
    __name__,
    external_stylesheets=[
        dbc.themes.BOOTSTRAP,
        "https://cdnjs.cloudflare.com/ajax/libs/font-awesome/6.0.0/css/all.min.css"
    ],
    suppress_callback_exceptions=True
)

app.title = "SIH Logistics Optimization Simulator"

# Global variables for storing data and results
current_data = None
current_solution = None
current_simulation = None
baseline_solution = None

# Initialize ETA predictor
eta_predictor = ETAPredictor()

def make_json_safe(value):
    """Recursively convert numpy/pandas objects to JSON-safe Python types."""
    if isinstance(value, dict):
        return {key: make_json_safe(val) for key, val in value.items()}
    if isinstance(value, (list, tuple, set)):
        return [make_json_safe(item) for item in value]
    if isinstance(value, (np.integer, np.int64, np.int32)):
        return int(value)
    if isinstance(value, (np.floating, np.float64, np.float32)):
        return float(value)
    if isinstance(value, (np.bool_,)):
        return bool(value)
    if isinstance(value, pd.Timestamp):
        return value.isoformat()
    if isinstance(value, pd.DataFrame):
        return value.to_dict("records")
    if isinstance(value, (pd.Series, pd.Index)):
        return value.tolist()
    return value


def get_data_frames(stored_data_json: Optional[str]) -> Dict[str, pd.DataFrame]:
    """Reconstruct dataframes from stored JSON string."""
    if not stored_data_json:
        return {}
    try:
        raw = json.loads(stored_data_json)
        return {key: pd.DataFrame(value) for key, value in raw.items()}
    except Exception as exc:
        print(f"Data reconstruction error: {exc}")
        return {}


def attach_solution_kpis(solution: Dict, data_frames: Dict[str, pd.DataFrame],
                         simulation_results: Optional[Dict] = None) -> Dict:
    """Compute and embed KPI metrics into the solution payload."""
    try:
        assignments = solution.get('assignments', [])
        vessels_df = data_frames.get('vessels', pd.DataFrame())
        plants_df = data_frames.get('plants', pd.DataFrame())
        ports_df = data_frames.get('ports', pd.DataFrame())
        rail_costs_df = data_frames.get('rail_costs', pd.DataFrame())

        kpis = calculate_kpis(
            assignments,
            vessels_df,
            plants_df,
            simulation_results,
            ports_df,
            rail_costs_df
        )
        solution['kpis'] = kpis
    except Exception as exc:
        print(f"Solution KPI attachment error: {exc}")
    return solution

def create_header():
    """Create application header"""
    return dbc.Navbar(
        dbc.Container([
            dbc.Row([
                dbc.Col([
                    html.I(className="fas fa-ship me-2"),
                    dbc.NavbarBrand("🚢 Port-Plant Logistics Optimization System", className="ms-2 fw-bold")
                ], width="auto"),
                dbc.Col([
                    dbc.Badge("SIH 2025", color="success", className="me-2"),
                    dbc.Badge("Steel Plant Logistics", color="primary")
                ], width="auto", className="ms-auto")
            ], align="center", className="w-100")
        ], fluid=True),
        color="primary",
        dark=True,
        className="mb-3"
    )

def create_controls_panel():
    """Create left controls panel"""
    return dbc.Card([
        dbc.CardHeader([
            html.I(className="fas fa-cogs me-2"),
            html.H5("Control Panel", className="mb-0")
        ]),
        dbc.CardBody([
            # Data Upload Section
            html.H6("📊 Data Management", className="text-primary mb-3"),
            dbc.ButtonGroup([
                dbc.Button("Load Sample Data", id="load-sample-btn", color="primary", size="sm"),
                dbc.Button("CSV Guide", id="csv-guide-btn", color="info", size="sm", outline=True)
            ], className="mb-3 w-100"),
            
            dcc.Upload(
                id='upload-data',
                children=html.Div([
                    html.I(className="fas fa-cloud-upload-alt fa-2x mb-2"),
                    html.Br(),
                    'Drag & Drop or ', html.A('Select CSV Files'),
                    html.Br(),
                    html.Small([
                        "Required: ",
                        html.Code("vessels.csv"),
                        ", ",
                        html.Code("ports.csv"),
                        ", ",
                        html.Code("plants.csv"),
                        ", ",
                        html.Code("rail_costs.csv")
                    ], className="text-muted")
                ]),
                style={
                    'width': '100%', 'minHeight': '120px', 'lineHeight': '1.5',
                    'borderWidth': '2px', 'borderStyle': 'dashed',
                    'borderRadius': '8px', 'textAlign': 'center', 
                    'padding': '20px', 'backgroundColor': '#f8f9fa'
                },
                multiple=True,
                className="mb-3"
            ),
            
            html.Div(id="data-status", className="mb-3"),
            
            dbc.Collapse([
                dbc.Card([
                    dbc.CardHeader("📋 CSV Format Guide", className="bg-info text-white"),
                    dbc.CardBody([
                        html.P("Required CSV files and their columns:", className="fw-bold"),
                        html.Ul([
                            html.Li([html.Code("vessels.csv"), ": vessel_id, cargo_mt, eta_day, port_id, demurrage_rate, cargo_grade"]),
                            html.Li([html.Code("ports.csv"), ": port_id, port_name, handling_cost_per_mt, daily_capacity_mt, rakes_available_per_day"]),
                            html.Li([html.Code("plants.csv"), ": plant_id, plant_name, daily_demand_mt, quality_requirements"]),
                            html.Li([html.Code("rail_costs.csv"), ": port_id, plant_id, cost_per_mt, distance_km, transit_days"])
                        ]),
                        dbc.Button("Download CSV Templates", id="download-templates-btn", color="info", size="sm", className="mt-2")
                    ])
                ])
            ], id="csv-guide-collapse", is_open=False, className="mb-3"),
            
            html.Hr(),
            
            # Optimization Settings
            html.H6("🧠 Optimization Settings", className="text-primary mb-3"),
            
            dbc.Label("Optimization Method:"),
            dcc.Dropdown(
                id="optimization-method",
                options=[
                    {"label": "MILP (Exact)", "value": "milp"},
                    {"label": "MILP + GA", "value": "milp_ga"},
                    {"label": "MILP + GA + SA", "value": "hybrid"},
                    {"label": "Genetic Algorithm Only", "value": "ga"}
                ],
                value="hybrid",
                className="mb-3"
            ),
            
            dbc.Label("Solver:"),
            dcc.Dropdown(
                id="solver-selection",
                options=[
                    {"label": "CBC (Free)", "value": "CBC"},
                    {"label": "Gurobi (Commercial)", "value": "GUROBI"}
                ],
                value="CBC",
                className="mb-3"
            ),
            
            dbc.Row([
                dbc.Col([
                    dbc.Label("Time Limit (s):"),
                    dbc.Input(id="time-limit", type="number", value=300, min=10, max=3600)
                ], width=6),
                dbc.Col([
                    dbc.Label("GA Generations:"),
                    dbc.Input(id="ga-generations", type="number", value=50, min=10, max=200)
                ], width=6)
            ], className="mb-3"),
            
            html.Hr(),
            
            # Scenario Settings
            html.H6("🎯 Scenario Analysis", className="text-primary mb-3"),
            
            dbc.Label("ETA Delay Scenario:"),
            dcc.Dropdown(
                id="eta-delay-scenario",
                options=[
                    {"label": "No Delays", "value": "none"},
                    {"label": "P10 (Minor)", "value": "P10"},
                    {"label": "P50 (Moderate)", "value": "P50"},
                    {"label": "P90 (Severe)", "value": "P90"}
                ],
                value="none",
                className="mb-3"
            ),
            
            dbc.Row([
                dbc.Col([
                    dbc.Label("Rake Reduction %:"),
                    dbc.Input(id="rake-reduction", type="number", value=0, min=0, max=50)
                ], width=6),
                dbc.Col([
                    dbc.Label("Demand Spike %:"),
                    dbc.Input(id="demand-spike", type="number", value=0, min=0, max=100)
                ], width=6)
            ], className="mb-3"),
            
            dbc.Label("Target Plant for Spike:"),
            dcc.Dropdown(id="spike-plant", className="mb-3"),
            
            html.Hr(),
            
            # Action Buttons
            html.H6("⚡ Actions", className="text-primary mb-3"),
            
            dbc.Button("🚀 Run Baseline (FCFS)", id="run-baseline-btn", color="secondary", size="sm", className="mb-2 w-100"),
            dbc.Button("✨ Run Optimized (AI)", id="run-optimized-btn", color="success", size="sm", className="mb-2 w-100"),
            dbc.Button("🔄 Run Simulation", id="run-simulation-btn", color="info", size="sm", className="mb-2 w-100"),
            dbc.Button("📊 Compare All Scenarios", id="compare-scenarios-btn", color="warning", size="sm", className="mb-3 w-100"),
            
            # Status indicator (replaces confusing progress bar)
            dbc.Alert(id="action-status", color="light", className="mb-3", style={"display": "none"}),
            
            # Export options
            html.Hr(),
            html.H6("📤 Export", className="text-primary mb-3"),
            dbc.ButtonGroup([
                dbc.Button("Export CSV", id="export-csv-btn", color="outline-dark", size="sm"),
                dbc.Button("Export SAP", id="export-sap-btn", color="outline-dark", size="sm")
            ], className="w-100")
        ])
    ], className="h-100")

def create_main_content():
    """Create main content area with tabs"""
    return dbc.Card([
        dbc.CardHeader([
            dbc.Tabs(
                id="main-tabs",
                active_tab="overview",
                children=[
                    dbc.Tab(label="📊 Overview", tab_id="overview"),
                    dbc.Tab(label="📅 Gantt & Schedules", tab_id="gantt"),
                    dbc.Tab(label="💰 Cost Breakdown", tab_id="costs"),
                    dbc.Tab(label="🚂 Rake Dashboard", tab_id="rakes"),
                    dbc.Tab(label="🔄 What-if Analysis", tab_id="whatif"),
                    dbc.Tab(label="📋 Logs & Export", tab_id="logs")
                ]
            )
        ]),
        dbc.CardBody([
            html.Div(id="tab-content")
        ])
    ])

def create_overview_tab():
    """Create overview tab content"""
    return html.Div([
        # KPI Cards Row
        dbc.Row(id="kpi-cards-row", className="mb-4"),
        
        # Charts Row
        dbc.Row([
            dbc.Col([
                dbc.Card([
                    dbc.CardHeader("System Status"),
                    dbc.CardBody([
                        html.Div(id="system-status")
                    ])
                ])
            ], width=4),
            dbc.Col([
                dbc.Card([
                    dbc.CardHeader("Quick Insights"),
                    dbc.CardBody([
                        html.Div(id="quick-insights")
                    ])
                ])
            ], width=8)
        ], className="mb-4"),
        
        # Data Summary
        dbc.Row([
            dbc.Col([
                dbc.Card([
                    dbc.CardHeader("Data Summary"),
                    dbc.CardBody([
                        html.Div(id="data-summary-table")
                    ])
                ])
            ], width=12)
        ])
    ])

def create_gantt_tab():
    """Create Gantt chart tab content"""
    return html.Div([
        dbc.Alert([
            html.H6([html.I(className="fas fa-info-circle me-2"), "Gantt Chart Guide"], className="mb-2"),
            html.P([
                "This timeline shows when each vessel arrives, unloads, and departs. ",
                "Each bar represents a vessel's complete cycle at port."
            ], className="mb-1"),
            html.Ul([
                html.Li("🟦 Blue bars: Vessel operations timeline"),
                html.Li("📍 Y-axis: Vessel IDs"),
                html.Li("📅 X-axis: Time (days)"),
                html.Li("Hover over bars for details (vessel, port, cargo, duration)")
            ], className="mb-0 small")
        ], color="info", className="mb-3"),
        
        dbc.Row([
            dbc.Col([
                dbc.Card([
                    dbc.CardHeader([
                        html.Div([
                            "🗓️ Vessel & Rake Schedule Timeline",
                            html.Span([
                                html.I(className="fas fa-info-circle chart-info-icon"),
                                html.Div([
                                    html.Strong("📊 How to Read This Chart"),
                                    html.P("Each horizontal bar represents a vessel's complete stay at port:", 
                                          style={'fontSize': '12px', 'marginTop': '6px'}),
                                    html.Ul([
                                        html.Li("Left edge: Vessel arrival (ETA)"),
                                        html.Li("Bar length: Time from arrival to departure"),
                                        html.Li("Color intensity: Cargo volume handled"),
                                        html.Li("Gaps between bars: Demurrage periods (delays)")
                                    ], style={'fontSize': '11px', 'paddingLeft': '18px'}),
                                    html.P("💡 Tip: Overlapping bars indicate concurrent berth usage. Longer bars may indicate bottlenecks.",
                                          style={'fontSize': '11px', 'marginTop': '8px', 'fontStyle': 'italic'})
                                ], className="chart-info-tooltip")
                            ], style={'position': 'relative', 'display': 'inline-block', 'marginLeft': '10px'})
                        ], style={'display': 'inline-block'}),
                        dbc.ButtonGroup([
                            dbc.Button([html.I(className="fas fa-sync me-1"), "Refresh"], 
                                      id="refresh-gantt-btn", size="sm", color="outline-primary"),
                            dbc.Button([html.I(className="fas fa-download me-1"), "Export"], 
                                      id="export-gantt-btn", size="sm", color="outline-secondary")
                        ], className="float-end")
                    ]),
                    dbc.CardBody([
                        dcc.Graph(id="gantt-chart", style={"height": "600px"})
                    ])
                ])
            ], width=12)
        ], className="mb-4"),
        
        dbc.Row([
            dbc.Col([
                dbc.Card([
                    dbc.CardHeader("📋 Schedule Details"),
                    dbc.CardBody([
                        html.Div(id="schedule-details")
                    ])
                ])
            ], width=6),
            dbc.Col([
                dbc.Card([
                    dbc.CardHeader("🔧 Schedule Summary"),
                    dbc.CardBody([
                        html.Div(id="schedule-summary")
                    ])
                ])
            ], width=6)
        ])
    ])

def create_cost_tab():
    """Create cost breakdown tab content"""
    return html.Div([
        dbc.Row([
            dbc.Col([
                dbc.Card([
                    dbc.CardHeader([
                        html.Div([
                            "💰 Cost Breakdown Analysis",
                            html.Span([
                                html.I(className="fas fa-info-circle chart-info-icon"),
                                html.Div([
                                    html.Strong("💵 Understanding Costs"),
                                    html.P("This chart shows the three main cost components:",
                                          style={'fontSize': '12px', 'marginTop': '6px'}),
                                    html.Ul([
                                        html.Li([html.Strong("Port Handling: "), "Cost to unload cargo at berth (₹/tonne)"]),
                                        html.Li([html.Strong("Rail Transport: "), "Cost to ship cargo inland by rail (₹/tonne-km)"]),
                                        html.Li([html.Strong("Demurrage: "), "Penalty for delays beyond scheduled time (₹/day per vessel)"])
                                    ], style={'fontSize': '11px', 'paddingLeft': '18px'}),
                                    html.P("⚠️ High demurrage indicates scheduling inefficiencies or berth congestion.",
                                          style={'fontSize': '11px', 'marginTop': '8px', 'fontStyle': 'italic', 'color': '#dc3545'})
                                ], className="chart-info-tooltip")
                            ], style={'position': 'relative', 'display': 'inline-block', 'marginLeft': '10px'})
                        ], style={'display': 'inline-block'})
                    ]),
                    dbc.CardBody([
                        dcc.Graph(id="cost-breakdown-chart", style={"height": "450px"})
                    ])
                ])
            ], width=8),
            dbc.Col([
                dbc.Card([
                    dbc.CardHeader("📊 Cost Drivers"),
                    dbc.CardBody([
                        html.Div(id="cost-drivers-analysis")
                    ])
                ])
            ], width=4)
        ], className="mb-4"),
        
        dbc.Row([
            dbc.Col([
                dbc.Card([
                    dbc.CardHeader("📈 Cost Timeline & Comparison"),
                    dbc.CardBody([
                        dcc.Graph(id="cost-timeline-chart", style={"height": "400px"})
                    ])
                ])
            ], width=12)
        ])
    ])

def create_rake_tab():
    """Create rake dashboard tab content"""
    return html.Div([
        dbc.Row([
            dbc.Col([
                dbc.Card([
                    dbc.CardHeader([
                        html.Div([
                            "🚂 Rake Utilization Heatmap",
                            html.Span([
                                html.I(className="fas fa-info-circle chart-info-icon"),
                                html.Div([
                                    html.Strong("🚆 Rake Usage Patterns"),
                                    html.P("This heatmap shows when and how often each rake is used:",
                                          style={'fontSize': '12px', 'marginTop': '6px'}),
                                    html.Ul([
                                        html.Li([html.Strong("Rows: "), "Individual rake IDs"]),
                                        html.Li([html.Strong("Columns: "), "Time periods (days or weeks)"]),
                                        html.Li([html.Strong("Color intensity: "), "Number of trips in that period (darker = more trips)"]),
                                        html.Li([html.Strong("White cells: "), "Rake idle during that time"])
                                    ], style={'fontSize': '11px', 'paddingLeft': '18px'}),
                                    html.P("🎯 Goal: Maximize color intensity uniformly to balance rake workload and increase utilization.",
                                          style={'fontSize': '11px', 'marginTop': '8px', 'fontStyle': 'italic'})
                                ], className="chart-info-tooltip")
                            ], style={'position': 'relative', 'display': 'inline-block', 'marginLeft': '10px'})
                        ], style={'display': 'inline-block'})
                    ]),
                    dbc.CardBody([
                        dcc.Graph(id="rake-heatmap", style={"height": "400px"})
                    ])
                ])
            ], width=8),
            dbc.Col([
                dbc.Card([
                    dbc.CardHeader("Rake Statistics"),
                    dbc.CardBody([
                        html.Div(id="rake-statistics")
                    ])
                ])
            ], width=4)
        ], className="mb-4"),
        
        dbc.Row([
            dbc.Col([
                dbc.Card([
                    dbc.CardHeader("Rake Assignment Table"),
                    dbc.CardBody([
                        html.Div(id="rake-assignment-table")
                    ])
                ])
            ], width=12)
        ])
    ])

# App Layout
app.layout = dbc.Container([
    create_header(),
    
    dbc.Row([
        dbc.Col([
            create_controls_panel()
        ], width=3),
        dbc.Col([
            create_main_content()
        ], width=9)
    ]),
    
    # Hidden divs for storing data
    html.Div(id="stored-data", style={"display": "none"}),
    html.Div(id="stored-solution", style={"display": "none"}),
    html.Div(id="stored-simulation", style={"display": "none"}),

    # Download targets (kept global so buttons work from any tab)
    dcc.Download(id="download-dispatch-csv-file"),
    dcc.Download(id="download-sap-file"),
    dcc.Download(id="download-full-report-file"),
    dcc.Download(id="download-gantt-csv"),
    dcc.Download(id="sample-csv-download"),
    
    # Interval component for progress updates
    dcc.Interval(id="progress-interval", interval=1000, n_intervals=0, disabled=True)
    
], fluid=True)

# Callbacks

@app.callback(
    [Output("stored-data", "children"),
     Output("data-status", "children"),
     Output("spike-plant", "options")],
    [Input("load-sample-btn", "n_clicks"),
     Input("upload-data", "contents")],
    [State("upload-data", "filename")]
)
def load_data(load_sample_clicks, upload_contents, upload_filenames):
    """Load sample data or process uploaded files"""
    global current_data
    
    ctx = callback_context
    if not ctx.triggered:
        return None, "", []
    
    trigger_id = ctx.triggered[0]["prop_id"].split(".")[0]
    
    if trigger_id == "load-sample-btn" and load_sample_clicks:
        # Load sample data
        current_data = DataLoader.get_toy_dataset()
        
        status = dbc.Alert([
            html.I(className="fas fa-check-circle me-2"),
            "Sample data loaded successfully!"
        ], color="success")
        
        # Plant options for spike scenario
        plant_options = [
            {"label": row['plant_name'], "value": row['plant_id']} 
            for _, row in current_data['plants'].iterrows()
        ]
        
        return json.dumps({k: v.to_dict('records') for k, v in current_data.items()}), status, plant_options
    
    elif trigger_id == "upload-data" and upload_contents:
        # Process uploaded files
        try:
            uploaded_data = {}
            for content, filename in zip(upload_contents, upload_filenames):
                df = DataLoader.parse_uploaded_file(content, filename)
                if df is not None:
                    # Determine dataset type from filename
                    if 'vessel' in filename.lower():
                        uploaded_data['vessels'] = df
                    elif 'port' in filename.lower():
                        uploaded_data['ports'] = df
                    elif 'plant' in filename.lower():
                        uploaded_data['plants'] = df
                    elif 'rail' in filename.lower():
                        uploaded_data['rail_costs'] = df
            
            # Validate uploaded data
            is_valid, errors = DataLoader.validate_csv_data(uploaded_data)
            
            if is_valid:
                current_data = uploaded_data
                status = dbc.Alert([
                    html.I(className="fas fa-check-circle me-2"),
                    f"Uploaded {len(uploaded_data)} datasets successfully!"
                ], color="success")
                
                plant_options = [
                    {"label": row.get('plant_name', row['plant_id']), "value": row['plant_id']} 
                    for _, row in current_data['plants'].iterrows()
                ]
                
                return json.dumps({k: v.to_dict('records') for k, v in current_data.items()}), status, plant_options
            else:
                status = dbc.Alert([
                    html.I(className="fas fa-exclamation-triangle me-2"),
                    html.Div([html.P(error) for error in errors])
                ], color="danger")
                
                return None, status, []
                
        except Exception as e:
            status = dbc.Alert([
                html.I(className="fas fa-exclamation-triangle me-2"),
                f"Error processing uploaded files: {str(e)}"
            ], color="danger")
            
            return None, status, []
    
    return None, "", []

# Toggle CSV guide
@app.callback(
    Output("csv-guide-collapse", "is_open"),
    [Input("csv-guide-btn", "n_clicks")],
    [State("csv-guide-collapse", "is_open")]
)
def toggle_csv_guide(n_clicks, is_open):
    """Toggle CSV format guide"""
    if n_clicks:
        return not is_open
    return is_open

@app.callback(
    Output("tab-content", "children"),
    [Input("main-tabs", "active_tab")]
)
def render_tab_content(active_tab):
    """Render content based on active tab"""
    if active_tab == "overview":
        return create_overview_tab()
    elif active_tab == "gantt":
        return create_gantt_tab()
    elif active_tab == "costs":
        return create_cost_tab()
    elif active_tab == "rakes":
        return create_rake_tab()
    elif active_tab == "whatif":
        return create_whatif_tab()
    elif active_tab == "logs":
        return create_logs_tab()
    else:
        return html.Div("Select a tab to view content")

def create_whatif_tab():
    """Create what-if analysis tab"""
    return html.Div([
        dbc.Alert([
            html.H6([html.I(className="fas fa-lightbulb me-2"), "What-If Analysis"], className="mb-2"),
            html.P("Compare different optimization scenarios side-by-side. Run baseline and optimized solutions to see comparisons.", className="mb-0")
        ], color="info", className="mb-3"),
        
        dbc.Row([
            dbc.Col([
                dbc.Card([
                    dbc.CardHeader("📊 Scenario Comparison"),
                    dbc.CardBody([
                        html.Div(id="scenario-comparison-summary")
                    ])
                ])
            ], width=12)
        ], className="mb-4"),
        
        dbc.Row([
            dbc.Col([
                dbc.Card([
                    dbc.CardHeader("📈 Scenario Impact Analysis"),
                    dbc.CardBody([
                        dcc.Graph(id="scenario-comparison-chart", style={"height": "500px"})
                    ])
                ])
            ], width=12)
        ])
    ])

def create_logs_tab():
    """Create logs and export tab"""
    return html.Div([
        dbc.Row([
            dbc.Col([
                dbc.Card([
                    dbc.CardHeader("📋 Optimization Logs"),
                    dbc.CardBody([
                        html.Div(id="solver-logs", style={"maxHeight": "300px", "overflowY": "auto"})
                    ])
                ])
            ], width=6),
            dbc.Col([
                dbc.Card([
                    dbc.CardHeader("📜 Audit Trail"),
                    dbc.CardBody([
                        html.Div(id="audit-trail")
                    ])
                ])
            ], width=6)
        ], className="mb-4"),
        
        dbc.Row([
            dbc.Col([
                dbc.Card([
                    dbc.CardHeader("📤 Export Options"),
                    dbc.CardBody([
                        html.H6("Download Results:", className="mb-3"),
                        dbc.ButtonGroup([
                            dbc.Button([html.I(className="fas fa-file-csv me-2"), "Dispatch Plan CSV"], 
                                      id="download-dispatch-csv", color="primary", className="mb-2"),
                            dbc.Button([html.I(className="fas fa-file-excel me-2"), "SAP Format"], 
                                      id="download-sap-format", color="secondary", className="mb-2"),
                            dbc.Button([html.I(className="fas fa-file-pdf me-2"), "Full Report"], 
                                      id="download-full-report", color="info", className="mb-2")
                        ], vertical=True, className="w-100"),
                        html.Hr(),
                        html.H6("Export Preview:", className="mt-3"),
                        html.Div(id="export-preview")
                    ])
                ])
            ], width=12)
        ])
    ])

@app.callback(
    [Output("stored-solution", "children"),
     Output("action-status", "children"),
     Output("action-status", "color"),
     Output("action-status", "style")],
    [Input("run-baseline-btn", "n_clicks"),
     Input("run-optimized-btn", "n_clicks")],
    [State("stored-data", "children"),
     State("optimization-method", "value"),
     State("solver-selection", "value"),
     State("time-limit", "value"),
     State("ga-generations", "value"),
     State("eta-delay-scenario", "value"),
     State("rake-reduction", "value"),
     State("demand-spike", "value"),
     State("spike-plant", "value")]
)
def run_optimization(baseline_clicks, optimized_clicks, stored_data, opt_method, 
                    solver, time_limit, ga_generations, eta_delay, rake_reduction, 
                    demand_spike, spike_plant):
    """Run optimization based on selected method"""
    global current_solution, baseline_solution
    
    ctx = callback_context
    if not ctx.triggered or not stored_data:
        return None, "", "light", {"display": "none"}
    
    trigger_id = ctx.triggered[0]["prop_id"].split(".")[0]
    
    try:
        # Reconstruct data from stored JSON
        data_dict = json.loads(stored_data)
        data = {k: pd.DataFrame(v) for k, v in data_dict.items()}
        
        # Apply scenario modifications
        if eta_delay != "none":
            data['vessels'] = ScenarioGenerator.apply_eta_delays(data['vessels'], eta_delay)
        
        if rake_reduction > 0:
            data['ports'] = ScenarioGenerator.reduce_rake_availability(data['ports'], rake_reduction)
        
        if demand_spike > 0 and spike_plant:
            data['plants'] = ScenarioGenerator.spike_plant_demand(data['plants'], spike_plant, demand_spike)
        
        if trigger_id == "run-baseline-btn":
            # Run baseline FCFS solution
            status_msg = html.Div([
                html.I(className="fas fa-spinner fa-spin me-2"),
                "Running baseline FCFS optimization..."
            ])
            status_color = "info"
            
            milp_optimizer = MILPOptimizer(data)
            solution = milp_optimizer.create_baseline_solution()
            solution = attach_solution_kpis(solution, data)
            solution = make_json_safe(solution)
            baseline_solution = solution
            current_solution = solution
            
            status_msg = html.Div([
                html.I(className="fas fa-check-circle me-2"),
                f"✅ Baseline completed! Cost: {format_currency(solution.get('objective_value', 0))}"
            ])
            status_color = "success"
            
        elif trigger_id == "run-optimized-btn":
            # Run selected optimization method
            status_msg = html.Div([
                html.I(className="fas fa-spinner fa-spin me-2"),
                f"Running {opt_method.upper()} optimization..."
            ])
            status_color = "info"
            
            if opt_method == "milp":
                milp_optimizer = MILPOptimizer(data)
                solution = milp_optimizer.solve_milp(solver, time_limit)
                
            elif opt_method == "ga":
                heuristic_optimizer = HeuristicOptimizer(data)
                solution = heuristic_optimizer.run_genetic_algorithm(
                    population_size=30, generations=ga_generations
                )
                
            elif opt_method == "milp_ga":
                # MILP + GA pipeline
                milp_optimizer = MILPOptimizer(data)
                milp_solution = milp_optimizer.solve_milp(solver, time_limit // 2)
                
                heuristic_optimizer = HeuristicOptimizer(data)
                solution = heuristic_optimizer.run_genetic_algorithm(
                    population_size=20, generations=ga_generations // 2,
                    seed_solution=milp_solution.get('assignments', [])
                )
                
            elif opt_method == "hybrid":
                # Full hybrid pipeline: MILP + GA + SA
                milp_optimizer = MILPOptimizer(data)
                milp_solution = milp_optimizer.solve_milp(solver, time_limit // 3)
                
                heuristic_optimizer = HeuristicOptimizer(data)
                ga_solution = heuristic_optimizer.run_genetic_algorithm(
                    population_size=20, generations=ga_generations // 2,
                    seed_solution=milp_solution.get('assignments', [])
                )
                
                solution = heuristic_optimizer.run_simulated_annealing(
                    ga_solution, max_iterations=500
                )
            
            solution = attach_solution_kpis(solution, data)
            solution = make_json_safe(solution)
            current_solution = solution
            
            # Calculate savings if baseline exists
            savings_msg = ""
            if baseline_solution:
                baseline_cost = baseline_solution.get('objective_value', 0)
                optimized_cost = solution.get('objective_value', 0)
                
                # Sanity checks
                if baseline_cost <= 0:
                    savings_msg = " | ⚠️ Warning: Baseline cost is zero or invalid"
                elif optimized_cost < 0:
                    savings_msg = " | ⚠️ Warning: Optimized cost is negative (solver error)"
                elif optimized_cost > baseline_cost:
                    # Optimization made it worse - this can happen with constraints
                    penalty = optimized_cost - baseline_cost
                    penalty_pct = (penalty / baseline_cost * 100)
                    savings_msg = f" | ⚠️ Cost increased by {format_currency(penalty)} (+{penalty_pct:.1f}%) - check constraints"
                else:
                    savings = baseline_cost - optimized_cost
                    savings_pct = (savings / baseline_cost * 100) if baseline_cost > 0 else 0
                    
                    # Cap at 95% for display (100% is impossible in real logistics)
                    if savings_pct > 95:
                        savings_msg = f" | 💰 Savings: {format_currency(savings)} (~{min(savings_pct, 99):.0f}% - exceptional!)"
                    else:
                        savings_msg = f" | 💰 Savings: {format_currency(savings)} ({savings_pct:.1f}%)"
            
            status_msg = html.Div([
                html.I(className="fas fa-check-circle me-2"),
                f"✅ Optimized! Cost: {format_currency(solution.get('objective_value', 0))}{savings_msg}"
            ])
            status_color = "success"
        
        # Store solution
        solution_json = json.dumps(solution, default=str)
        
        return solution_json, status_msg, status_color, {"display": "block"}
        
    except Exception as e:
        error_msg = html.Div([
            html.I(className="fas fa-exclamation-triangle me-2"),
            f"❌ Error: {str(e)}"
        ])
        return None, error_msg, "danger", {"display": "block"}

@app.callback(
    [Output("stored-simulation", "children")],
    [Input("run-simulation-btn", "n_clicks")],
    [State("stored-data", "children"),
     State("stored-solution", "children")]
)
def run_simulation(simulation_clicks, stored_data, stored_solution):
    """Run discrete-time simulation"""
    global current_simulation, current_solution
    
    if not simulation_clicks or not stored_data or not stored_solution:
        return [None]
    
    try:
        # Reconstruct data and solution
        data = get_data_frames(stored_data)
        
        solution = json.loads(stored_solution)
        assignments = solution.get('assignments', [])
        
        # Run simulation
        simulator = LogisticsSimulator(data, time_step_hours=6)
        simulation_results = simulator.run_simulation(assignments, simulation_days=30)
        simulation_results = make_json_safe(simulation_results)
        
        current_simulation = simulation_results

        # Refresh current solution KPIs with simulation insights
        global current_solution
        if current_solution:
            enriched_solution = attach_solution_kpis(current_solution, data, simulation_results)
            current_solution = make_json_safe(enriched_solution)
            # Also update stored_solution payload so UI consumers get the latest KPI mix
            solution = current_solution
        
        return [json.dumps(simulation_results)]
        
    except Exception as e:
        print(f"Simulation error: {e}")
        return [None]


@app.callback(
    Output("download-dispatch-csv-file", "data"),
    [Input("download-dispatch-csv", "n_clicks"),
     Input("export-csv-btn", "n_clicks")],
    [State("stored-solution", "children"),
     State("stored-simulation", "children"),
     State("stored-data", "children")]
)
def download_dispatch_csv(_export_logs_clicks, _export_sidebar_clicks, stored_solution, stored_simulation, stored_data):
    ctx = callback_context
    if not ctx.triggered or not stored_solution:
        return None

    trigger_id = ctx.triggered[0]["prop_id"].split(".")[0]

    try:
        solution = json.loads(stored_solution)
        assignments = solution.get('assignments', [])
        if not assignments:
            return None

        df = pd.DataFrame(assignments)

        # If triggered from the main sidebar button, provide a richer export bundle
        if trigger_id == "export-csv-btn":
            buffer = io.BytesIO()
            with zipfile.ZipFile(buffer, mode="w", compression=zipfile.ZIP_DEFLATED) as zip_buffer:
                zip_buffer.writestr("dispatch_plan.csv", df.to_csv(index=False))

                # Include KPI summary if simulation has been run
                simulation = json.loads(stored_simulation) if stored_simulation else {}
                if not isinstance(simulation, dict):
                    simulation = {}

                data_frames = get_data_frames(stored_data)
                kpis = solution.get('kpis', {}) or simulation.get('kpis', {})
                if not kpis and data_frames:
                    kpis = calculate_kpis(
                        assignments,
                        data_frames.get('vessels', pd.DataFrame()),
                        data_frames.get('plants', pd.DataFrame()),
                        simulation.get('kpis'),
                        data_frames.get('ports', pd.DataFrame()),
                        data_frames.get('rail_costs', pd.DataFrame())
                    )
                if kpis:
                    kpi_df = pd.DataFrame([kpis])
                    zip_buffer.writestr("kpi_summary.csv", kpi_df.to_csv(index=False))

                # Include assignment aggregation by port/plant
                if not df.empty:
                    summary_df = (
                        df.groupby(['port_id', 'plant_id'], dropna=False)
                          .agg(assignments=('vessel_id', 'count'), cargo_mt=('cargo_mt', 'sum'))
                          .reset_index()
                    )
                    zip_buffer.writestr("port_plant_summary.csv", summary_df.to_csv(index=False))

                # Include a simple readme for context
                summary_lines = [
                    "SIH Logistics Optimization Export",
                    "This archive contains the current dispatch plan and KPIs.",
                    "Files:",
                    "- dispatch_plan.csv: Vessel to plant assignments with timing.",
                    "- kpi_summary.csv: Key performance indicators (if available).",
                    "Generated by the sidebar Export CSV button.",
                    f"Assignments exported: {len(df)}"
                ]
                zip_buffer.writestr("README.txt", "\n".join(summary_lines))

            buffer.seek(0)
            return dcc.send_bytes(buffer.getvalue(), "dispatch_export_bundle.zip")

        # Default: simple CSV download from the Logs & Export tab
        return dcc.send_data_frame(df.to_csv, filename="dispatch_plan.csv", index=False)

    except Exception as e:
        print(f"Dispatch export error: {e}")
        return None


@app.callback(
    Output("download-sap-file", "data"),
    [Input("download-sap-format", "n_clicks"),
     Input("export-sap-btn", "n_clicks")],
    [State("stored-solution", "children"),
     State("stored-data", "children")]
)
def download_sap_format(_export_logs_clicks, _export_sidebar_clicks, stored_solution, stored_data):
    ctx = callback_context
    if not ctx.triggered or not stored_solution or not stored_data:
        return None

    trigger_id = ctx.triggered[0]["prop_id"].split(".")[0]

    try:
        solution = json.loads(stored_solution)
        data_dict = json.loads(stored_data)
        vessels = pd.DataFrame(data_dict.get('vessels', []))
        assignments = pd.DataFrame(solution.get('assignments', []))
        if assignments.empty:
            return None

        # Simple SAP-like flat export (placeholder fields)
        sap = assignments.merge(vessels[['vessel_id', 'eta_day', 'port_id']].drop_duplicates(), on='vessel_id', how='left')
        sap = sap.rename(columns={
            'vessel_id': 'Vessel',
            'port_id': 'Port',
            'plant_id': 'Plant',
            'cargo_mt': 'Quantity_MT',
            'time_period': 'Planned_Day',
            'berth_time': 'Planned_Berth_Day'
        })
        cols = ['Vessel', 'Port', 'Plant', 'Quantity_MT', 'Planned_Day', 'Planned_Berth_Day', 'eta_day']
        for c in cols:
            if c not in sap.columns:
                sap[c] = None
        sap = sap[cols]

        if trigger_id == "export-sap-btn":
            buffer = io.BytesIO()
            with zipfile.ZipFile(buffer, mode="w", compression=zipfile.ZIP_DEFLATED) as zip_buffer:
                zip_buffer.writestr("sap_dispatch_template.csv", sap.to_csv(index=False))

                # Provide vessel meta sheet for planners
                if not vessels.empty:
                    meta_cols = ['_id', 'vessel_id', 'cargo_mt', 'eta_day', 'port_id', 'demurrage_rate']
                    available_meta_cols = [col for col in meta_cols if col in vessels.columns]
                    if available_meta_cols:
                        vessel_meta = vessels[available_meta_cols].copy()
                        if '_id' in vessel_meta.columns:
                            vessel_meta = vessel_meta.rename(columns={'_id': 'RecordID'})
                        zip_buffer.writestr("vessel_metadata.csv", vessel_meta.to_csv(index=False))

                assignments = solution.get('assignments', [])
                if assignments:
                    plan_df = pd.DataFrame(assignments)
                    zip_buffer.writestr("assignment_details.csv", plan_df.to_csv(index=False))

                instructions = [
                    "SAP Upload Package",
                    "Use sap_dispatch_template.csv to upload into SAP.",
                    "Reference vessel_metadata.csv for demurrage and ETA information.",
                    "Generated via the sidebar Export SAP button."
                ]
                zip_buffer.writestr("README.txt", "\n".join(instructions))

            buffer.seek(0)
            return dcc.send_bytes(buffer.getvalue(), "sap_export_bundle.zip")

        # Default export pathway
        return dcc.send_data_frame(sap.to_csv, filename="dispatch_sap_export.csv", index=False)
    except Exception as e:
        print(f"SAP export error: {e}")
        return None


@app.callback(
    Output("download-full-report-file", "data"),
    [Input("download-full-report", "n_clicks")],
    [State("stored-solution", "children"), State("stored-simulation", "children")]
)
def download_full_report(n_clicks, stored_solution, stored_simulation):
    if not n_clicks or not stored_solution:
        return None
    try:
        solution = json.loads(stored_solution)
        sim = json.loads(stored_simulation) if stored_simulation else {}
        report = {
            'solution_summary': {k: v for k, v in solution.items() if k != 'assignments'},
            'kpis': (sim.get('kpis') if sim else {}),
            'cost_components': (sim.get('cost_components') if sim else {}),
        }
        import io
        buf = io.StringIO()
        import json as _json
        buf.write(_json.dumps(report, indent=2))
        return dict(content=buf.getvalue(), filename="full_report.json")
    except Exception:
        return None

@app.callback(
    Output("kpi-cards-row", "children"),
    [Input("stored-solution", "children"),
     Input("stored-simulation", "children")],
    [State("stored-data", "children")]
)
def update_kpi_cards(stored_solution, stored_simulation, stored_data):
    """Update KPI cards in overview tab"""
    if not stored_solution:
        return []
    
    try:
        solution = json.loads(stored_solution)
        assignments = solution.get('assignments', [])
        simulation_results = json.loads(stored_simulation) if stored_simulation else None
        data_frames = {}
        if stored_data:
            data_dict = json.loads(stored_data)
            data_frames = {k: pd.DataFrame(v) for k, v in data_dict.items()}
        vessels_df = data_frames.get('vessels', pd.DataFrame())
        plants_df = data_frames.get('plants', pd.DataFrame())
        ports_df = data_frames.get('ports', pd.DataFrame())
        rail_costs_df = data_frames.get('rail_costs', pd.DataFrame())
        
        kpis = calculate_kpis(
            assignments,
            vessels_df,
            plants_df,
            simulation_results,
            ports_df,
            rail_costs_df
        )
        
        # If no simulation has been run yet, fall back to solution objective
        if not stored_simulation:
            kpis['total_cost'] = kpis.get('total_cost', solution.get('objective_value', 0))
            kpis['demurrage_cost'] = kpis.get('demurrage_cost', 0.0)
        
        # Get baseline KPIs for comparison
        baseline_kpis = None
        if baseline_solution:
            baseline_assignments = baseline_solution.get('assignments', [])
            baseline_kpis = calculate_kpis(
                baseline_assignments,
                vessels_df,
                plants_df,
                None,
                ports_df,
                rail_costs_df
            )
        
        # Create KPI cards
        cards_data = LogisticsVisualizer.create_kpi_cards(kpis, baseline_kpis)
        
        cards = []
        for card_data in cards_data:
            # Determine delta color and icon - CORRECTED LOGIC
            # Lower is better: Total Cost, Demurrage, Avg Wait
            # Higher is better: Demand Fulfillment, Rake Utilization, Vessels Processed
            
            delta_color = "secondary"
            delta_icon = "fas fa-minus"
            
            if card_data['delta'] is not None and card_data['delta'] != 0:
                # Metrics where LOWER is BETTER (costs, delays)
                if card_data['title'] in ['Total Cost', 'Demurrage Cost', 'Avg Vessel Wait']:
                    if card_data['delta'] < 0:  # Decreased = Good
                        delta_color = "success"
                        delta_icon = "fas fa-arrow-down"
                    else:  # Increased = Bad
                        delta_color = "danger"
                        delta_icon = "fas fa-arrow-up"
                
                # Metrics where HIGHER is BETTER (fulfillment, utilization, efficiency)
                else:  # Demand Fulfillment, Rake Utilization, Vessels Processed
                    if card_data['delta'] > 0:  # Increased = Good
                        delta_color = "success"
                        delta_icon = "fas fa-arrow-up"
                    else:  # Decreased = Bad
                        delta_color = "danger"
                        delta_icon = "fas fa-arrow-down"
            
            # Create delta display
            delta_display = ""
            if card_data['delta'] is not None:
                delta_display = html.Div([
                    html.I(className=f"{delta_icon} me-1"),
                    html.Span(f"{card_data['delta_pct']:+.1f}%", className=f"text-{delta_color}")
                ], className="mt-1")
            
            # Build tooltip content (less flashy, more readable)
            tooltip_content = html.Div([
                html.Div(card_data.get('tooltip_title', card_data['title']), 
                        className="kpi-tooltip-title"),
                html.Div([
                    html.Strong("Formula: "),
                    html.Div(card_data.get('formula', 'N/A'), className="kpi-tooltip-formula")
                ]),
                html.Div([
                    html.P(card_data.get('description', ''), 
                          style={'marginTop': '8px', 'fontSize': '12px', 'lineHeight': '1.5'})
                ]),
                html.Div([
                    html.Strong("Key Factors:", style={'display': 'block', 'marginTop': '10px', 'marginBottom': '6px'}),
                    html.Div([
                        html.Div([
                            html.I(className="fas fa-check-circle", 
                                  style={'width': '20px', 'color': '#28a745', 'marginRight': '8px'}),
                            html.Span(factor, style={'fontSize': '12px'})
                        ], className="kpi-tooltip-factor") 
                        for factor in card_data.get('factors', [])
                    ], className="kpi-tooltip-factors")
                ])
            ], className="kpi-tooltip")
            
            # Special styling for demurrage card (less flashy)
            card_classes = f"kpi-card kpi-card-{card_data['color']} h-100"
            if card_data.get('is_demurrage') and card_data['raw_value'] > 0:
                card_classes += " demurrage-card"
            
            # Demurrage badge for non-zero values
            demurrage_badge = None
            if card_data.get('is_demurrage') and card_data['raw_value'] > 0:
                demurrage_badge = html.Div("⚠️ PENALTY", className="demurrage-badge", 
                                          style={'fontSize': '11px', 'padding': '4px 8px'})
            
            card = dbc.Col([
                dbc.Card([
                    dbc.CardBody([
                        tooltip_content,
                        demurrage_badge if demurrage_badge else None,
                        html.Div([
                            html.I(className=f"{card_data['icon']} fa-2x mb-2", 
                                  style={'color': f'var(--bs-{card_data["color"]})'}),
                            html.H3(card_data['value'], className="kpi-value mb-1"),
                            html.P(card_data['title'], className="text-muted mb-1 fw-semibold"),
                            delta_display
                        ], className="text-center", style={'position': 'relative', 'zIndex': 1})
                    ], style={'position': 'relative'})
                ], className=card_classes, style={'minHeight': '200px'})
            ], width=2)
            
            cards.append(card)
        
        return cards
        
    except Exception as e:
        print(f"KPI cards error: {e}")
        return []

def build_gantt_dataframe(stored_solution: Optional[str], stored_data: Optional[str]) -> pd.DataFrame:
    """Generate a normalized dataframe used by gantt chart and exports."""
    if not stored_solution or not stored_data:
        return pd.DataFrame()

    try:
        solution = json.loads(stored_solution)
        data_dict = json.loads(stored_data)

        assignments = solution.get('assignments', [])
        if not assignments:
            return pd.DataFrame()

        vessels_df = pd.DataFrame(data_dict.get('vessels', []))
        if vessels_df.empty:
            return pd.DataFrame()

        rows = []
        for assign in assignments:
            vessel_id = assign.get('vessel_id', 'Unknown')
            vessel_row = vessels_df[vessels_df['vessel_id'] == vessel_id]
            if vessel_row.empty:
                continue

            eta_day = vessel_row.iloc[0].get('eta_day', 0)
            try:
                eta_day = float(eta_day)
            except (TypeError, ValueError):
                continue

            cargo_mt = assign.get('cargo_mt', 0)
            try:
                cargo_mt = float(cargo_mt)
            except (TypeError, ValueError):
                cargo_mt = 0.0

            processing_days = max(1.0, cargo_mt / 10000.0) if cargo_mt else 1.0

            rows.append({
                'Vessel': vessel_id,
                'Port': assign.get('port_id', 'Unknown'),
                'Plant': assign.get('plant_id', 'Unknown'),
                'CargoMT': cargo_mt,
                'StartDay': eta_day,
                'FinishDay': eta_day + processing_days,
                'DurationDays': processing_days
            })

        return pd.DataFrame(rows)

    except Exception as e:
        print(f"Gantt data build error: {e}")
        return pd.DataFrame()


@app.callback(
    Output("gantt-chart", "figure"),
    [Input("stored-solution", "children"),
     Input("refresh-gantt-btn", "n_clicks")],
    [State("stored-data", "children")]
)
def update_gantt_chart(stored_solution, refresh_clicks, stored_data):
    """Update Gantt chart with detailed vessel schedules"""
    if not stored_solution or not stored_data:
        return go.Figure().add_annotation(
            text="Run an optimization to see vessel schedule",
            xref="paper", yref="paper",
            x=0.5, y=0.5, showarrow=False,
            font=dict(size=14, color="gray")
        )
    
    try:
        gantt_df = build_gantt_dataframe(stored_solution, stored_data)

        if gantt_df.empty:
            return go.Figure().add_annotation(
                text="No vessel assignments found",
                xref="paper", yref="paper",
                x=0.5, y=0.5, showarrow=False
            )

        # Create figure
        fig = go.Figure()
        
        # Color map for ports
        port_colors = {
            'HALDIA': '#007bff',
            'PARADIP': '#28a745',
            'VIZAG': '#ffc107',
            'MUMBAI': '#dc3545',
            'CHENNAI': '#17a2b8'
        }
        
        gantt_records = gantt_df.to_dict('records')
        for i, row in enumerate(gantt_records):
            color = port_colors.get(row['Port'], '#6c757d')
            
            fig.add_trace(go.Bar(
                x=[row['FinishDay'] - row['StartDay']],
                y=[row['Vessel']],
                base=row['StartDay'],
                orientation='h',
                marker=dict(color=color),
                name=row['Port'],
                showlegend=(i == 0 or row['Port'] not in [gantt_records[j]['Port'] for j in range(i)]),
                hovertemplate=f"<b>{row['Vessel']}</b><br>" +
                             f"Port: {row['Port']}<br>" +
                             f"Plant: {row['Plant']}<br>" +
                             f"Cargo: {row['CargoMT']:,.0f} MT<br>" +
                             f"Days {row['StartDay']:.1f} - {row['FinishDay']:.1f}<br>" +
                             f"Duration: {row['DurationDays']:.1f} days<extra></extra>"
            ))
        
        fig.update_layout(
            title="Vessel Processing Timeline",
            xaxis_title="Time (Days)",
            yaxis_title="Vessels",
            barmode='overlay',
            height=580,
            showlegend=True,
            legend=dict(title="Ports", orientation="h", y=1.1),
            hovermode='closest'
        )
        
        return fig
        
    except Exception as e:
        print(f"Gantt chart error: {e}")
        return go.Figure().add_annotation(
            text=f"Error creating chart: {str(e)}",
            xref="paper", yref="paper",
            x=0.5, y=0.5, showarrow=False,
            font=dict(size=12, color="red")
        )


@app.callback(
    Output("download-gantt-csv", "data"),
    [Input("export-gantt-btn", "n_clicks")],
    [State("stored-solution", "children"),
     State("stored-data", "children")]
)
def download_gantt_csv(n_clicks, stored_solution, stored_data):
    if not n_clicks or not stored_solution or not stored_data:
        return None

    gantt_df = build_gantt_dataframe(stored_solution, stored_data)
    if gantt_df.empty:
        return None

    try:
        buffer = io.BytesIO()
        with zipfile.ZipFile(buffer, mode="w", compression=zipfile.ZIP_DEFLATED) as zip_buffer:
            zip_buffer.writestr("gantt_schedule.csv", gantt_df.to_csv(index=False))

            port_summary = gantt_df.groupby('Port').agg(
                Vessels=('Vessel', 'count'),
                TotalCargoMT=('CargoMT', 'sum'),
                AvgDurationDays=('DurationDays', 'mean')
            ).reset_index()
            zip_buffer.writestr("port_summary.csv", port_summary.to_csv(index=False))

            plant_summary = gantt_df.groupby('Plant').agg(
                Vessels=('Vessel', 'count'),
                TotalCargoMT=('CargoMT', 'sum'),
                AvgDurationDays=('DurationDays', 'mean')
            ).reset_index()
            zip_buffer.writestr("plant_summary.csv", plant_summary.to_csv(index=False))

            readme = [
                "Gantt Schedule Export Package",
                "Included files:",
                "- gantt_schedule.csv: Detailed vessel timeline.",
                "- port_summary.csv: Aggregated stats per port.",
                "- plant_summary.csv: Aggregated stats per plant.",
                "Generated via the Gantt tab export button."
            ]
            zip_buffer.writestr("README.txt", "\n".join(readme))

        buffer.seek(0)
        return dcc.send_bytes(buffer.getvalue(), "gantt_schedule_export.zip")
    except Exception as e:
        print(f"Gantt export error: {e}")
        return None


@app.callback(
    [Output("schedule-details", "children"),
     Output("schedule-summary", "children")],
    [Input("stored-solution", "children")],
    [State("stored-data", "children")]
)
def update_schedule_info(stored_solution, stored_data):
    """Update schedule details and summary"""
    if not stored_solution or not stored_data:
        return "No schedule available", "No summary available"
    
    try:
        solution = json.loads(stored_solution)
        data_dict = json.loads(stored_data)
        assignments = solution.get('assignments', [])
        vessels_df = pd.DataFrame(data_dict['vessels'])
        
        # Schedule details table
        details_data = []
        for assign in assignments[:10]:  # Show first 10
            vessel_id = assign.get('vessel_id', 'N/A')
            vessel_row = vessels_df[vessels_df['vessel_id'] == vessel_id]
            eta = vessel_row.iloc[0]['eta_day'] if not vessel_row.empty else 'N/A'
            
            details_data.append({
                'Vessel': vessel_id,
                'ETA Day': f"{eta:.1f}" if isinstance(eta, (int, float)) else eta,
                'Port': assign.get('port_id', 'N/A'),
                'Plant': assign.get('plant_id', 'N/A')
            })
        
        details_df = pd.DataFrame(details_data)
        details_table = dash_table.DataTable(
            data=details_df.to_dict('records'),
            columns=[{'name': col, 'id': col} for col in details_df.columns],
            style_cell={'textAlign': 'left', 'padding': '8px', 'fontSize': '13px'},
            style_header={'backgroundColor': '#343a40', 'color': 'white', 'fontWeight': 'bold'},
            style_data_conditional=[
                {'if': {'row_index': 'odd'}, 'backgroundColor': '#f8f9fa'}
            ],
            page_size=10
        )
        
        # Summary stats
        total_vessels = len(assignments)
        ports_used = len(set(a.get('port_id') for a in assignments))
        plants_served = len(set(a.get('plant_id') for a in assignments))
        
        summary = html.Div([
            html.H6("📊 Schedule Statistics", className="mb-3"),
            dbc.ListGroup([
                dbc.ListGroupItem([
                    html.Strong("Total Vessels Scheduled: "),
                    html.Span(f"{total_vessels}", className="float-end badge bg-primary")
                ]),
                dbc.ListGroupItem([
                    html.Strong("Ports Utilized: "),
                    html.Span(f"{ports_used}", className="float-end badge bg-success")
                ]),
                dbc.ListGroupItem([
                    html.Strong("Plants Served: "),
                    html.Span(f"{plants_served}", className="float-end badge bg-info")
                ]),
                dbc.ListGroupItem([
                    html.Strong("Avg Vessels per Port: "),
                    html.Span(f"{total_vessels/ports_used:.1f}" if ports_used > 0 else "N/A", 
                             className="float-end badge bg-secondary")
                ])
            ])
        ])
        
        return details_table, summary
        
    except Exception as e:
        return f"Error: {str(e)}", f"Error: {str(e)}"

@app.callback(
    [Output("scenario-comparison-summary", "children"),
     Output("scenario-comparison-chart", "figure")],
    [Input("stored-solution", "children"),
     Input("compare-scenarios-btn", "n_clicks")]
)
def update_scenario_comparison(stored_solution, compare_clicks):
    """Compare baseline vs optimized scenarios"""
    if not stored_solution:
        msg = html.P("Run baseline and optimized solutions to compare scenarios", className="text-muted text-center p-4")
        fig = go.Figure().add_annotation(
            text="Run optimizations to see comparison",
            xref="paper", yref="paper", x=0.5, y=0.5, showarrow=False
        )
        return msg, fig
    
    try:
        solution = json.loads(stored_solution)
        
        # Build comparison data
        scenarios = []
        costs = []
        vessels = []
        
        if baseline_solution:
            scenarios.append('Baseline (FCFS)')
            costs.append(baseline_solution.get('objective_value', 0))
            vessels.append(len(baseline_solution.get('assignments', [])))
        
        if current_solution:
            scenarios.append('Optimized (AI)')
            costs.append(current_solution.get('objective_value', 0))
            vessels.append(len(current_solution.get('assignments', [])))
        
        if len(scenarios) < 2:
            msg = html.Div([
                dbc.Alert("Run both Baseline and Optimized to see full comparison", color="warning"),
                html.P(f"Currently have: {', '.join(scenarios) if scenarios else 'None'}")
            ])
            fig = go.Figure().add_annotation(
                text="Run both baseline and optimized solutions",
                xref="paper", yref="paper", x=0.5, y=0.5, showarrow=False
            )
            return msg, fig
        
        # Summary cards
        baseline_cost = costs[0] if len(costs) > 0 else 0
        optimized_cost = costs[1] if len(costs) > 1 else 0
        savings = baseline_cost - optimized_cost
        savings_pct = (savings / baseline_cost * 100) if baseline_cost > 0 else 0
        
        # Sanity check and display appropriate message
        savings_color = "success"
        savings_text = f"{savings_pct:.1f}% reduction"
        
        if baseline_cost <= 0:
            savings_text = "Invalid baseline cost"
            savings_color = "danger"
        elif optimized_cost > baseline_cost:
            savings_color = "danger"
            savings_text = f"{abs(savings_pct):.1f}% increase (worse)"
        elif savings_pct > 95:
            savings_text = f"~{min(savings_pct, 99):.0f}% reduction (exceptional!)"
            savings_color = "warning"
        
        summary = dbc.Row([
            dbc.Col([
                dbc.Card([
                    dbc.CardHeader("Baseline (FCFS)", className="bg-secondary text-white"),
                    dbc.CardBody([
                        html.H4(format_currency(baseline_cost), className="text-secondary"),
                        html.P(f"{vessels[0]} vessels", className="text-muted mb-0")
                    ])
                ])
            ], width=4),
            dbc.Col([
                dbc.Card([
                    dbc.CardHeader("Optimized (AI)", className="bg-success text-white"),
                    dbc.CardBody([
                        html.H4(format_currency(optimized_cost), className="text-success"),
                        html.P(f"{vessels[1]} vessels", className="text-muted mb-0")
                    ])
                ])
            ], width=4),
            dbc.Col([
                dbc.Card([
                    dbc.CardHeader("💰 Savings", className=f"bg-{savings_color} text-white"),
                    dbc.CardBody([
                        html.H4(format_currency(savings), className=f"text-{savings_color}"),
                        html.P(savings_text, className="text-muted mb-0")
                    ])
                ])
            ], width=4)
        ])
        
        # Create comparison chart
        fig = make_subplots(
            rows=1, cols=2,
            subplot_titles=('Cost Comparison', 'Vessel Utilization'),
            specs=[[{'type': 'bar'}, {'type': 'bar'}]]
        )
        
        # Cost comparison
        fig.add_trace(
            go.Bar(
                x=scenarios,
                y=costs,
                marker=dict(color=['#6c757d', '#28a745']),
                text=[format_currency(c) for c in costs],
                textposition='outside',
                name='Cost'
            ),
            row=1, col=1
        )
        
        # Vessel utilization
        fig.add_trace(
            go.Bar(
                x=scenarios,
                y=vessels,
                marker=dict(color=['#ffc107', '#007bff']),
                text=vessels,
                textposition='outside',
                name='Vessels'
            ),
            row=1, col=2
        )
        
        fig.update_layout(
            height=450,
            showlegend=False,
            title_text="Scenario Analysis Dashboard"
        )
        
        fig.update_yaxes(title_text="Total Cost (₹)", row=1, col=1)
        fig.update_yaxes(title_text="Vessels Processed", row=1, col=2)
        
        return summary, fig
        
    except Exception as e:
        print(f"Scenario comparison error: {e}")
        msg = html.P(f"Error: {str(e)}", className="text-danger")
        fig = go.Figure().add_annotation(
            text=f"Error: {str(e)}",
            xref="paper", yref="paper", x=0.5, y=0.5, showarrow=False,
            font=dict(color="red")
        )
        return msg, fig

@app.callback(
    Output("cost-breakdown-chart", "figure"),
    [Input("stored-solution", "children"),
     Input("stored-simulation", "children")],
    [State("stored-data", "children")]
)
def update_cost_breakdown(stored_solution, stored_simulation, stored_data):
    """Update cost breakdown chart - now truly dynamic"""
    if not stored_solution:
        return go.Figure().add_annotation(
            text="Run an optimization to see cost breakdown",
            xref="paper", yref="paper",
            x=0.5, y=0.5, showarrow=False,
            font=dict(size=14, color="gray")
        )
    
    try:
        solution = json.loads(stored_solution)
        data_dict = json.loads(stored_data)
        
        # Calculate detailed costs from solution
        assignments = solution.get('assignments', [])
        vessels_df = pd.DataFrame(data_dict['vessels'])
        ports_df = pd.DataFrame(data_dict['ports'])
        rail_costs_df = pd.DataFrame(data_dict['rail_costs'])
        
        # Calculate component costs
        port_handling_cost = 0
        rail_transport_cost = 0
        demurrage_cost = 0
        
        for assign in assignments:
            vessel_id = assign.get('vessel_id')
            port_id = assign.get('port_id')
            plant_id = assign.get('plant_id')
            cargo_mt = assign.get('cargo_mt', 0)
            
            # Port handling
            port_row = ports_df[ports_df['port_id'] == port_id]
            if not port_row.empty:
                handling_rate = port_row.iloc[0]['handling_cost_per_mt']
                port_handling_cost += cargo_mt * handling_rate
            
            # Rail transport
            rail_row = rail_costs_df[
                (rail_costs_df['port_id'] == port_id) & 
                (rail_costs_df['plant_id'] == plant_id)
            ]
            if not rail_row.empty:
                rail_rate = rail_row.iloc[0]['cost_per_mt']
                rail_transport_cost += cargo_mt * rail_rate
            
            # Demurrage (simplified - would need actual wait times)
            vessel_row = vessels_df[vessels_df['vessel_id'] == vessel_id]
            if not vessel_row.empty:
                demurrage_rate = vessel_row.iloc[0]['demurrage_rate']
                # Estimate 0.5 day average delay
                demurrage_cost += demurrage_rate * 12  # 12 hours estimated wait
        
        # Create pie chart
        labels = ['Port Handling', 'Rail Transport', 'Demurrage', 'Other']
        values = [
            port_handling_cost,
            rail_transport_cost,
            demurrage_cost,
            max(0, solution.get('objective_value', 0) - port_handling_cost - rail_transport_cost - demurrage_cost)
        ]
        
        fig = go.Figure(data=[go.Pie(
            labels=labels,
            values=values,
            hole=0.4,
            marker=dict(colors=['#007bff', '#28a745', '#ffc107', '#6c757d']),
            textinfo='label+percent',
            textposition='outside'
        )])
        
        fig.update_layout(
            title={
                'text': f'Cost Breakdown - Total: {format_currency(sum(values))}',
                'x': 0.5,
                'xanchor': 'center'
            },
            showlegend=True,
            height=450
        )
        
        return fig
        
    except Exception as e:
        print(f"Cost breakdown error: {e}")
        return go.Figure().add_annotation(
            text=f"Error: {str(e)}",
            xref="paper", yref="paper",
            x=0.5, y=0.5, showarrow=False,
            font=dict(size=12, color="red")
        )

@app.callback(
    Output("cost-drivers-analysis", "children"),
    [Input("stored-solution", "children")],
    [State("stored-data", "children")]
)
def update_cost_drivers(stored_solution, stored_data):
    """Analyze and display key cost drivers"""
    if not stored_solution or not stored_data:
        return html.P("No data available", className="text-muted")
    
    try:
        solution = json.loads(stored_solution)
        data_dict = json.loads(stored_data)
        
        drivers = []
        
        # Port utilization driver
        assignments = solution.get('assignments', [])
        port_counts = {}
        for assign in assignments:
            port = assign.get('port_id', 'Unknown')
            port_counts[port] = port_counts.get(port, 0) + 1
        
        if port_counts:
            max_port = max(port_counts, key=port_counts.get)
            drivers.append(
                html.Div([
                    html.H6([html.I(className="fas fa-anchor me-2"), "Port Utilization"], className="text-primary"),
                    html.P(f"Busiest: {max_port} ({port_counts[max_port]} vessels)", className="mb-1"),
                    html.Small(f"Total ports used: {len(port_counts)}", className="text-muted")
                ], className="mb-3")
            )
        
        # Cargo distribution
        total_cargo = sum(assign.get('cargo_mt', 0) for assign in assignments)
        if total_cargo > 0:
            drivers.append(
                html.Div([
                    html.H6([html.I(className="fas fa-boxes me-2"), "Cargo Volume"], className="text-success"),
                    html.P(f"Total: {total_cargo:,.0f} MT", className="mb-1"),
                    html.Small(f"Avg per vessel: {total_cargo/len(assignments):,.0f} MT", className="text-muted")
                ], className="mb-3")
            )
        
        # Cost per MT insight
        total_cost = solution.get('objective_value', 0)
        if total_cargo > 0:
            cost_per_mt = total_cost / total_cargo
            drivers.append(
                html.Div([
                    html.H6([html.I(className="fas fa-calculator me-2"), "Efficiency"], className="text-info"),
                    html.P(f"Cost per MT: ₹{cost_per_mt:.2f}", className="mb-1"),
                    html.Small("Lower is better", className="text-muted")
                ], className="mb-3")
            )
        
        return drivers
        
    except Exception as e:
        return html.P(f"Error: {str(e)}", className="text-danger")

@app.callback(
    Output("cost-timeline-chart", "figure"),
    [Input("stored-solution", "children")],
    [State("stored-data", "children")]
)
def update_cost_timeline(stored_solution, stored_data):
    """Create cost timeline and baseline comparison"""
    if not stored_solution:
        return go.Figure().add_annotation(
            text="Run optimization to see cost timeline",
            xref="paper", yref="paper",
            x=0.5, y=0.5, showarrow=False
        )
    
    try:
        solution = json.loads(stored_solution)
        
        # Create comparison chart if baseline exists
        scenarios = ['Current Solution']
        costs = [solution.get('objective_value', 0)]
        colors = ['#28a745']
        
        if baseline_solution:
            scenarios.insert(0, 'Baseline (FCFS)')
            costs.insert(0, baseline_solution.get('objective_value', 0))
            colors.insert(0, '#6c757d')
        
        # Create bar chart
        fig = go.Figure(data=[
            go.Bar(
                x=scenarios,
                y=costs,
                marker=dict(color=colors),
                text=[format_currency(c) for c in costs],
                textposition='outside'
            )
        ])
        
        # Add savings annotation if baseline exists
        if baseline_solution and len(costs) > 1:
            savings = costs[0] - costs[1]
            savings_pct = (savings / costs[0] * 100) if costs[0] > 0 else 0
            
            fig.add_annotation(
                x=1, y=costs[1],
                text=f"💰 Savings: {format_currency(savings)}<br>({savings_pct:.1f}% reduction)",
                showarrow=True,
                arrowhead=2,
                arrowcolor='green',
                font=dict(size=12, color='green'),
                bgcolor='rgba(200,255,200,0.8)',
                bordercolor='green'
            )
        
        fig.update_layout(
            title="Cost Comparison Across Scenarios",
            yaxis_title="Total Cost (₹)",
            showlegend=False,
            height=380,
            margin=dict(t=50, b=50)
        )
        
        return fig
        
    except Exception as e:
        print(f"Cost timeline error: {e}")
        return go.Figure().add_annotation(
            text=f"Error: {str(e)}",
            xref="paper", yref="paper",
            x=0.5, y=0.5, showarrow=False,
            font=dict(size=12, color="red")
        )

@app.callback(
    Output("rake-heatmap", "figure"),
    [Input("stored-solution", "children")],
    [State("stored-data", "children")]
)
def update_rake_heatmap(stored_solution, stored_data):
    """Update rake utilization heatmap"""
    if not stored_solution or not stored_data:
        return go.Figure()
    
    try:
        solution = json.loads(stored_solution)
        data_dict = json.loads(stored_data)
        
        assignments = solution.get('assignments', [])
        ports_df = pd.DataFrame(data_dict['ports'])
        
        return LogisticsVisualizer.create_rake_heatmap(assignments, ports_df)
        
    except Exception as e:
        print(f"Rake heatmap error: {e}")
        return go.Figure()


@app.callback(
    [Output("rake-statistics", "children"),
     Output("rake-assignment-table", "children")],
    [Input("stored-solution", "children"),
     Input("stored-simulation", "children")],
    [State("stored-data", "children")]
)
def update_rake_panels(stored_solution, stored_simulation, stored_data):
    """Render rake summary stats and detailed assignment table."""
    if not stored_solution:
        empty_msg = html.P("Run an optimization to view rake utilization", className="text-muted")
        return empty_msg, empty_msg

    try:
        solution = json.loads(stored_solution)
        assignments = solution.get('assignments', [])

        if not assignments:
            empty_msg = html.P("No rake movements planned.", className="text-muted")
            return empty_msg, empty_msg

        df = pd.DataFrame(assignments)

        # Compute stats
        total_rakes = int(df.get('rakes_required', pd.Series(dtype=int)).sum()) if 'rakes_required' in df else 0
        total_cargo = float(df.get('cargo_mt', pd.Series(dtype=float)).sum()) if 'cargo_mt' in df else 0.0
        unique_ports = df['port_id'].nunique() if 'port_id' in df else 0
        unique_plants = df['plant_id'].nunique() if 'plant_id' in df else 0

        simulation = json.loads(stored_simulation) if stored_simulation else {}
        kpis = simulation.get('kpis', {}) if isinstance(simulation, dict) else {}
        rake_utilization = kpis.get('avg_rake_utilization')

        stats_items = []
        stats_items.append(dbc.ListGroupItem([
            html.Strong("Total Rakes Scheduled"),
            html.Span(f"{total_rakes}", className="badge bg-primary float-end")
        ]))
        stats_items.append(dbc.ListGroupItem([
            html.Strong("Cargo Moved"),
            html.Span(f"{total_cargo:,.0f} MT", className="badge bg-success float-end")
        ]))
        stats_items.append(dbc.ListGroupItem([
            html.Strong("Ports Involved"),
            html.Span(str(unique_ports), className="badge bg-info float-end")
        ]))
        stats_items.append(dbc.ListGroupItem([
            html.Strong("Plants Served"),
            html.Span(str(unique_plants), className="badge bg-warning text-dark float-end")
        ]))
        if rake_utilization is not None:
            stats_items.append(dbc.ListGroupItem([
                html.Strong("Average Rake Utilization"),
                html.Span(f"{rake_utilization:.2%}", className="badge bg-secondary float-end")
            ]))

        stats_component = dbc.ListGroup(stats_items, flush=True)

        # Prepare detailed table
        display_df = df.rename(columns={
            'vessel_id': 'Vessel',
            'port_id': 'Port',
            'plant_id': 'Plant',
            'cargo_mt': 'Cargo (MT)',
            'rakes_required': 'Rakes Required',
            'scheduled_day': 'Scheduled Day',
            'berth_time': 'Berth Day',
            'eta_day': 'ETA Day'
        })

        display_columns = [col for col in ['Vessel', 'Port', 'Plant', 'Cargo (MT)',
                                           'Rakes Required', 'Scheduled Day', 'Berth Day', 'ETA Day']
                           if col in display_df.columns]

        table = dash_table.DataTable(
            data=display_df[display_columns].to_dict('records'),
            columns=[{'name': col, 'id': col} for col in display_columns],
            page_size=10,
            style_cell={'textAlign': 'left', 'padding': '8px', 'fontSize': 12},
            style_header={'backgroundColor': '#0d6efd', 'color': 'white', 'fontWeight': 'bold'},
            style_data_conditional=[
                {'if': {'row_index': 'odd'}, 'backgroundColor': '#f8f9fa'}
            ],
            sort_action='native'
        )

        return stats_component, table

    except Exception as exc:
        error = html.P(f"Error building rake metrics: {exc}", className="text-danger")
        return error, error

@app.callback(
    Output("system-status", "children"),
    [Input("stored-data", "children"),
     Input("stored-solution", "children"),
     Input("stored-simulation", "children")]
)
def update_system_status(stored_data, stored_solution, stored_simulation):
    """Update system status display"""
    status_items = []
    
    # Data status
    if stored_data:
        status_items.append(
            html.Div([
                html.I(className="fas fa-check-circle text-success me-2"),
                "Data loaded"
            ])
        )
    else:
        status_items.append(
            html.Div([
                html.I(className="fas fa-times-circle text-danger me-2"),
                "No data loaded"
            ])
        )
    
    # Solution status
    if stored_solution:
        solution = json.loads(stored_solution)
        status_items.append(
            html.Div([
                html.I(className="fas fa-check-circle text-success me-2"),
                f"Optimization: {solution.get('status', 'Unknown')}"
            ])
        )
    else:
        status_items.append(
            html.Div([
                html.I(className="fas fa-times-circle text-warning me-2"),
                "No optimization run"
            ])
        )
    
    # Simulation status
    if stored_simulation:
        status_items.append(
            html.Div([
                html.I(className="fas fa-check-circle text-success me-2"),
                "Simulation completed"
            ])
        )
    else:
        status_items.append(
            html.Div([
                html.I(className="fas fa-times-circle text-warning me-2"),
                "No simulation run"
            ])
        )
    
    return status_items

@app.callback(
    Output("quick-insights", "children"),
    [Input("stored-solution", "children"),
     Input("stored-simulation", "children")],
    [State("stored-data", "children")]
)
def update_quick_insights(stored_solution, stored_simulation, stored_data):
    """Generate quick insights from optimization results"""
    if not stored_solution or not stored_data:
        return html.Div([
            html.I(className="fas fa-info-circle me-2"),
            "Run an optimization to see insights"
        ], className="text-muted")
    
    try:
        solution = json.loads(stored_solution)
        data_dict = json.loads(stored_data)
        
        insights = []
        
        # Cost efficiency insight
        total_cost = solution.get('objective_value', 0)
        if baseline_solution:
            baseline_cost = baseline_solution.get('objective_value', 0)
            if baseline_cost > 0:
                improvement = ((baseline_cost - total_cost) / baseline_cost) * 100
                if improvement > 10:
                    insights.append(
                        dbc.Alert([
                            html.I(className="fas fa-trophy me-2"),
                            f"Excellent! {improvement:.1f}% cost reduction vs baseline"
                        ], color="success", className="mb-2")
                    )
                elif improvement > 0:
                    insights.append(
                        dbc.Alert([
                            html.I(className="fas fa-check me-2"),
                            f"Good! {improvement:.1f}% cost reduction vs baseline"
                        ], color="info", className="mb-2")
                    )
        
        # Vessel utilization insight
        assignments = solution.get('assignments', [])
        if assignments:
            vessels_df = pd.DataFrame(data_dict['vessels'])
            processed = len(assignments)
            total = len(vessels_df)
            utilization = (processed / total) * 100
            
            insights.append(
                dbc.Alert([
                    html.I(className="fas fa-ship me-2"),
                    f"Processing {processed}/{total} vessels ({utilization:.0f}% utilization)"
                ], color="primary" if utilization > 80 else "warning", className="mb-2")
            )
        
        # Bottleneck detection
        ports_df = pd.DataFrame(data_dict['ports'])
        if len(ports_df) > 0:
            port_assignments = {}
            for assign in assignments:
                port = assign.get('port_id', 'Unknown')
                port_assignments[port] = port_assignments.get(port, 0) + 1
            
            if port_assignments:
                max_port = max(port_assignments, key=port_assignments.get)
                max_count = port_assignments[max_port]
                avg_count = sum(port_assignments.values()) / len(port_assignments)
                
                if max_count > avg_count * 1.5:
                    insights.append(
                        dbc.Alert([
                            html.I(className="fas fa-exclamation-triangle me-2"),
                            f"Potential bottleneck: {max_port} handling {max_count} vessels"
                        ], color="warning", className="mb-2")
                    )
        
        # Optimization method insight
        opt_status = solution.get('status', 'Unknown')
        solver_time = solution.get('solve_time', 0)
        insights.append(
            dbc.Alert([
                html.I(className="fas fa-cog me-2"),
                f"Status: {opt_status} | Solve time: {solver_time:.2f}s"
            ], color="secondary", className="mb-2")
        )
        
        if not insights:
            insights.append(
                html.Div([
                    html.I(className="fas fa-chart-line me-2"),
                    "Analysis in progress..."
                ], className="text-muted")
            )
        
        return insights
        
    except Exception as e:
        return html.Div([
            html.I(className="fas fa-exclamation-circle me-2"),
            f"Error generating insights: {str(e)}"
        ], className="text-danger")

@app.callback(
    Output("data-summary-table", "children"),
    [Input("stored-data", "children")]
)
def update_data_summary(stored_data):
    """Create data summary table"""
    if not stored_data:
        return html.Div([
            html.I(className="fas fa-database me-2"),
            "No data loaded. Click 'Load Sample Data' or upload CSV files."
        ], className="text-muted text-center p-4")
    
    try:
        data_dict = json.loads(stored_data)
        
        summary_rows = []
        for dataset_name, records in data_dict.items():
            df = pd.DataFrame(records)
            summary_rows.append({
                'Dataset': dataset_name.upper(),
                'Records': len(df),
                'Columns': len(df.columns),
                'Key Columns': ', '.join(df.columns[:3].tolist())
            })
        
        summary_df = pd.DataFrame(summary_rows)
        
        return dash_table.DataTable(
            data=summary_df.to_dict('records'),
            columns=[{'name': col, 'id': col} for col in summary_df.columns],
            style_cell={'textAlign': 'left', 'padding': '10px'},
            style_header={'backgroundColor': '#343a40', 'color': 'white', 'fontWeight': 'bold'},
            style_data_conditional=[
                {'if': {'row_index': 'odd'}, 'backgroundColor': '#f8f9fa'}
            ]
        )
        
    except Exception as e:
        return html.Div([
            html.I(className="fas fa-exclamation-circle me-2"),
            f"Error: {str(e)}"
        ], className="text-danger")

@app.callback(
    [Output("solver-logs", "children"),
     Output("audit-trail", "children")],
    [Input("stored-solution", "children"),
     Input("stored-simulation", "children")]
)
def update_logs_and_audit(stored_solution, stored_simulation):
    """Update solver logs and audit trail"""
    logs = []
    audit = []
    
    if stored_solution:
        try:
            solution = json.loads(stored_solution)
            
            # Solver logs
            log_entries = solution.get('logs', [])
            if log_entries:
                for entry in log_entries:
                    logs.append(html.P(entry, className="mb-1 font-monospace small"))
            else:
                # Generate synthetic logs from solution
                logs.append(html.P(f"✓ Optimization method: {solution.get('method', 'N/A')}", className="mb-1"))
                logs.append(html.P(f"✓ Status: {solution.get('status', 'N/A')}", className="mb-1"))
                logs.append(html.P(f"✓ Objective value: {format_currency(solution.get('objective_value', 0))}", className="mb-1"))
                logs.append(html.P(f"✓ Solve time: {solution.get('solve_time', 0):.2f}s", className="mb-1"))
                logs.append(html.P(f"✓ Assignments: {len(solution.get('assignments', []))} vessels", className="mb-1"))
            
            # Audit trail
            import datetime
            timestamp = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            audit.append(
                dbc.ListGroupItem([
                    html.Div([
                        html.Strong("Optimization Completed"),
                        html.Br(),
                        html.Small(f"Time: {timestamp}", className="text-muted"),
                        html.Br(),
                        html.Small(f"Method: {solution.get('method', 'Unknown')}", className="text-muted"),
                        html.Br(),
                        html.Small(f"Cost: {format_currency(solution.get('objective_value', 0))}", className="text-muted")
                    ])
                ])
            )
            
        except Exception as e:
            logs.append(html.P(f"Error parsing solution: {str(e)}", className="text-danger"))
    
    if stored_simulation:
        try:
            simulation = json.loads(stored_simulation)
            import datetime
            timestamp = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            audit.append(
                dbc.ListGroupItem([
                    html.Div([
                        html.Strong("Simulation Completed"),
                        html.Br(),
                        html.Small(f"Time: {timestamp}", className="text-muted"),
                        html.Br(),
                        html.Small(f"Duration: {simulation.get('simulation_days', 'N/A')} days", className="text-muted")
                    ])
                ])
            )
        except:
            pass
    
    if not logs:
        logs = [html.P("No logs available. Run an optimization first.", className="text-muted")]
    
    if not audit:
        audit = [html.P("No activities yet.", className="text-muted")]
    
    return logs, dbc.ListGroup(audit)

@app.callback(
    Output("export-preview", "children"),
    [Input("stored-solution", "children")],
    [State("stored-data", "children")]
)
def update_export_preview(stored_solution, stored_data):
    """Show preview of exportable data"""
    if not stored_solution or not stored_data:
        return html.P("Run an optimization to preview export data", className="text-muted")
    
    try:
        solution = json.loads(stored_solution)
        assignments = solution.get('assignments', [])
        
        if not assignments:
            return html.P("No assignments to export", className="text-muted")
        
        # Create preview dataframe
        preview_data = []
        for i, assign in enumerate(assignments[:5]):  # Show first 5
            preview_data.append({
                'Vessel': assign.get('vessel_id', 'N/A'),
                'Port': assign.get('port_id', 'N/A'),
                'Plant': assign.get('plant_id', 'N/A'),
                'Cargo (MT)': f"{assign.get('cargo_mt', 0):,.0f}",
                'ETA Day': assign.get('eta_day', 'N/A')
            })
        
        preview_df = pd.DataFrame(preview_data)
        
        result = [
            html.P(f"Preview (showing 5 of {len(assignments)} assignments):", className="small text-muted mb-2"),
            dash_table.DataTable(
                data=preview_df.to_dict('records'),
                columns=[{'name': col, 'id': col} for col in preview_df.columns],
                style_cell={'textAlign': 'left', 'padding': '8px', 'fontSize': '12px'},
                style_header={'backgroundColor': '#6c757d', 'color': 'white', 'fontWeight': 'bold'},
                style_data_conditional=[
                    {'if': {'row_index': 'odd'}, 'backgroundColor': '#f8f9fa'}
                ]
            )
        ]
        
        return result
        
    except Exception as e:
        return html.P(f"Error: {str(e)}", className="text-danger")

def run_server(debug=None, port=None, host=None):
    """Run the Dash server"""
    from config import get_port, get_host, get_debug, get_dashboard_url
    import os
    import logging
    
    # Use provided values or fall back to config
    actual_port = port or get_port()
    actual_host = host or get_host()
    actual_debug = debug if debug is not None else get_debug()
    
    # Reduce Flask/Werkzeug logging noise (keeps errors, hides routine logs)
    log = logging.getLogger('werkzeug')
    log.setLevel(logging.ERROR)  # Only show errors, not every HTTP request
    
    print("🚢🚂 Starting SIH Logistics Optimization Simulator...")
    print(f"📊 Dashboard will be available at: http://{actual_host}:{actual_port}/")
    print("🔧 Loading modules and initializing ML models...")
    
    # Initialize ML model (guard against duplicate execution under any reloader)
    # Even though we disable the reloader, keep this guard for safety.
    if os.environ.get("WERKZEUG_RUN_MAIN") in (None, "true"):
        eta_predictor.train_stub_model()
    
    print(f"✅ Ready! Open your browser to http://{actual_host}:{actual_port}/")
    print("💡 Tip: The app is running silently. Check browser for UI updates.")
    print("⚠️  Errors (if any) will still appear here.\n")
    
    # Explicitly disable the reloader to prevent the app from starting twice.
    # Also disable Dash dev hot reload to avoid duplicate side effects.
    try:
        app.run(
            debug=actual_debug,
            host=actual_host,
            port=actual_port,
            use_reloader=False,
            dev_tools_hot_reload=False,
        )
    except TypeError:
        # Fallback for older Dash versions that may not support all kwargs
        app.run(
            debug=actual_debug,
            host=actual_host,
            port=actual_port,
            use_reloader=False,
        )

if __name__ == "__main__":
    run_server()
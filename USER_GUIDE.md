# 🚢🚂 SIH Logistics Optimization Simulator - User Guide

## Quick Start

### 1. Launch the Application

```bash
python app.py
```

Then open your browser to: **http://127.0.0.1:5006/**

### 2. Load Data

**Option A: Use Sample Data (Recommended for first-time users)**
- Click **"Load Sample Data"** button in the Control Panel
- Sample data includes 10 vessels, 3 ports, 5 plants with realistic logistics data

**Option B: Upload Your Own CSV Files**
1. Click **"CSV Guide"** to see required format
2. Prepare 4 CSV files:
   - `vessels.csv` - Vessel information
   - `ports.csv` - Port capabilities
   - `plants.csv` - Plant demands
   - `rail_costs.csv` - Rail transport costs
3. Drag & drop or select files in the upload area

### 3. Run Optimization

**Baseline (FCFS)**
- Click **🚀 Run Baseline (FCFS)** for First-Come-First-Served allocation
- Shows current/naive cost without AI optimization

**Optimized (AI)**
- Click **✨ Run Optimized (AI)** for intelligent optimization
- Uses hybrid MILP + Genetic Algorithm + Simulated Annealing
- Automatically shows cost savings vs baseline

### 4. Analyze Results

Navigate through tabs to explore different views:

---

## 📊 Features Guide

### Overview Tab
**What you'll see:**
- **KPI Cards** - Real-time metrics with baseline comparison
  - Total Cost
  - Demurrage Cost
  - Demand Fulfillment %
  - Average Vessel Wait Time
  - Rake Utilization
  - Vessels Processed
  
- **System Status** - Current state of data, optimization, simulation

- **Quick Insights** - AI-generated observations:
  - Cost reduction percentage
  - Vessel utilization rate
  - Bottleneck detection
  - Optimization performance

- **Data Summary** - Loaded datasets overview

**How to use:**
1. Load data first
2. Run baseline and/or optimized
3. KPIs update automatically
4. Green arrows = improvement, Red arrows = degradation

---

### 📅 Gantt & Schedules Tab

**What you'll see:**
- **Interactive Gantt Chart**
  - Each bar = one vessel's processing timeline
  - Colors represent different ports
  - X-axis = Time (days)
  - Y-axis = Vessel IDs
  - Hover over bars for details

- **Schedule Details Table**
  - Vessel assignments
  - ETA days
  - Port and plant allocations

- **Schedule Summary**
  - Total vessels scheduled
  - Ports utilized
  - Plants served
  - Average vessels per port

**How to read the Gantt chart:**
- 🟦 Blue bars = Haldia Port
- 🟩 Green bars = Paradip Port  
- 🟨 Yellow bars = Vizag Port
- Longer bars = more cargo/processing time
- Hover for: vessel ID, port, plant, cargo MT, duration

---

### 💰 Cost Breakdown Tab

**What you'll see:**
- **Cost Pie Chart** - Dynamically calculated from actual solution
  - Port Handling Costs
  - Rail Transport Costs
  - Demurrage Costs
  - Other Costs
  
- **Cost Drivers Analysis**
  - Port utilization insights
  - Cargo volume statistics
  - Cost per MT efficiency metric

- **Cost Timeline & Comparison**
  - Bar chart comparing baseline vs optimized
  - Savings amount and percentage
  - Visual cost reduction impact

**Understanding costs:**
- **Port Handling**: cargo × port handling rate
- **Rail Transport**: cargo × rail cost per MT (port→plant)
- **Demurrage**: vessel delays × demurrage rate
- Lower total = better optimization

---

### 🚂 Rake Dashboard Tab

**What you'll see:**
- **Rake Utilization Heatmap**
  - Shows which ports/days have rake capacity constraints
  - Warmer colors = higher utilization
  
- **Rake Statistics**
  - Available rakes per day per port
  - Utilization percentages

- **Rake Assignment Table**
  - Detailed rake allocations

**Why rakes matter:**
- Rakes transport cargo from ports to plants
- Limited rakes = bottleneck
- Optimization balances vessel scheduling with rake availability

---

### 🔄 What-if Analysis Tab

**What you'll see:**
- **Scenario Comparison Cards**
  - Baseline (FCFS) cost & vessels
  - Optimized (AI) cost & vessels
  - Savings calculation

- **Impact Analysis Charts**
  - Side-by-side cost comparison
  - Vessel utilization comparison

**How to use:**
1. Run both baseline and optimized
2. Navigate to What-if tab
3. See automatic comparison
4. Click **📊 Compare All Scenarios** for refresh

**Interpreting results:**
- Green card (Optimized) should be lower cost
- Savings card shows absolute and percentage reduction
- If savings are negative, baseline was already optimal (rare)

---

### 📋 Logs & Export Tab

**What you'll see:**
- **Optimization Logs**
  - Solver status
  - Optimization method used
  - Solve time
  - Number of assignments

- **Audit Trail**
  - Timestamped activity log
  - Optimization completion events
  - Simulation completion events

- **Export Options**
  - **Dispatch Plan CSV**: Vessel-port-plant assignments
  - **SAP Format**: Enterprise system compatible format
  - **Full Report**: Comprehensive PDF report

- **Export Preview**
  - Shows first 5 assignments
  - Verify data before downloading

**How to export:**
1. Run optimization first
2. Navigate to Logs & Export tab
3. Preview appears automatically
4. Click desired export button
5. File downloads to your browser's download folder

---

## 🎛️ Advanced Settings

### Optimization Method
- **MILP (Exact)**: Mathematical programming, finds provably optimal solution
- **MILP + GA**: Combines exact method with genetic algorithm for speed
- **MILP + GA + SA**: Full hybrid (recommended), best balance of quality and speed
- **Genetic Algorithm Only**: Heuristic-based, fast but approximate

### Solver Selection
- **CBC (Free)**: Open-source, works for most problems
- **Gurobi (Commercial)**: Faster, requires license (if installed)

### Time Limit
- How long solver can run (10-3600 seconds)
- Longer = potentially better solution
- 300s default is good balance

### GA Generations
- Genetic algorithm iterations (10-200)
- More = better exploration but slower
- 50 default works well

### Scenario Analysis Settings
- **ETA Delay Scenario**: Simulate vessel delays
  - None: No artificial delays
  - P10: 10th percentile (minor delays)
  - P50: Median delays
  - P90: 90th percentile (severe delays)

- **Rake Reduction %**: Reduce rake availability (0-50%)
  - Tests system resilience to capacity constraints

- **Demand Spike %**: Increase plant demand (0-100%)
  - Select target plant
  - Tests handling of demand surge

---

## 📝 CSV File Format Reference

### vessels.csv
```csv
vessel_id,cargo_mt,eta_day,port_id,demurrage_rate,cargo_grade
MV_IRON_1,25000,1,HALDIA,5000,IRON_ORE
MV_COAL_1,30000,2,PARADIP,6000,COAL
```

**Columns:**
- `vessel_id`: Unique identifier (string)
- `cargo_mt`: Cargo in metric tons (integer)
- `eta_day`: Estimated arrival day (integer, 1-365)
- `port_id`: Destination port (must match ports.csv)
- `demurrage_rate`: Cost per hour of delay (float, ₹)
- `cargo_grade`: Type of cargo (IRON_ORE, COAL, etc.)

### ports.csv
```csv
port_id,port_name,handling_cost_per_mt,daily_capacity_mt,rakes_available_per_day
HALDIA,Haldia Port,25.0,50000,8
PARADIP,Paradip Port,22.0,60000,10
```

**Columns:**
- `port_id`: Unique identifier (string)
- `port_name`: Display name (string)
- `handling_cost_per_mt`: Cost to handle 1 MT (float, ₹)
- `daily_capacity_mt`: Max MT per day (integer)
- `rakes_available_per_day`: Number of rail rakes available daily (integer)

### plants.csv
```csv
plant_id,plant_name,daily_demand_mt,quality_requirements
PLANT_A,Steel Plant A,8000,IRON_ORE
PLANT_B,Steel Plant B,6000,COAL
```

**Columns:**
- `plant_id`: Unique identifier (string)
- `plant_name`: Display name (string)
- `daily_demand_mt`: Daily material demand (integer)
- `quality_requirements`: Required cargo type (must match cargo_grade)

### rail_costs.csv
```csv
port_id,plant_id,cost_per_mt,distance_km,transit_days
HALDIA,PLANT_A,95.50,450,2
HALDIA,PLANT_B,120.30,680,2
```

**Columns:**
- `port_id`: Source port (must match ports.csv)
- `plant_id`: Destination plant (must match plants.csv)
- `cost_per_mt`: Transport cost per MT (float, ₹)
- `distance_km`: Distance (integer, km)
- `transit_days`: Travel time (integer, days)

---

## 🎯 Best Practices

### Getting Started
1. **Start with sample data** to understand the system
2. **Run baseline first** to establish a reference point
3. **Then run optimized** to see improvements
4. **Compare scenarios** to quantify benefits

### Optimization Tips
1. **Use hybrid method** for best results (default)
2. **Increase time limit** for larger datasets (e.g., 600s)
3. **Check quick insights** for bottleneck warnings
4. **Review Gantt chart** to verify realistic schedules

### Data Preparation
1. **Ensure all IDs match** across CSV files
2. **Use realistic costs** for meaningful results
3. **Include all ports** that vessels can use
4. **Define all plant demands** accurately

### Troubleshooting
- **"No module named 'dash'"**: Run `pip install -r requirements_dash.txt`
- **No data showing**: Check CSV format matches guide
- **Optimization fails**: Reduce time limit or check data validity
- **Costs don't change**: Ensure you clicked the optimization button and solution completed

---

## 🚀 Performance Tips

### For Large Datasets (100+ vessels)
- Use **MILP + GA** instead of full hybrid
- Increase **time limit** to 600-900 seconds
- Reduce **GA generations** to 30-40
- Split analysis into smaller time windows

### For Real-Time Use
- Keep **time limit** at 120-180 seconds
- Use **GA only** for fastest results
- Pre-load and cache data
- Export results periodically

---

## 💡 Understanding the Results

### What makes a good solution?
1. **Low total cost** - primary objective
2. **High demand fulfillment** - all plants served
3. **Low demurrage** - vessels processed quickly
4. **Balanced port utilization** - no bottlenecks
5. **High rake utilization** - efficient resource use

### Red flags to watch for:
- ⚠️ Vessels waiting >24 hours at port
- ⚠️ Ports processing >80% of all vessels (bottleneck)
- ⚠️ Plants with <90% demand fulfillment
- ⚠️ Demurrage costs >30% of total cost
- ⚠️ Rake utilization <50% (inefficient) or >95% (constraint)

---

## 📞 Support

For issues, questions, or feature requests:
1. Check this guide first
2. Review sample data format
3. Verify CSV file structure
4. Check browser console for errors (F12)

---

## 🎓 Technical Details

### Optimization Algorithms
- **MILP**: Mixed Integer Linear Programming using PuLP/CBC
- **GA**: Genetic Algorithm using DEAP library
- **SA**: Simulated Annealing for local refinement

### Cost Components
```
Total Cost = Port Handling + Rail Transport + Demurrage + Penalties
```

### Constraints Enforced
- Port daily capacity limits
- Rake availability per port
- Plant quality requirements (cargo matching)
- Vessel ETA scheduling
- Conservation of flow

---

**Version**: 1.0  
**Last Updated**: October 2025  
**Author**: SIH Logistics Optimization Team

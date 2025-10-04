# Cost Calculation & Optimization Guide

## Overview
This document explains how costs are calculated in the SIH Logistics Optimization Simulator and what realistic optimization savings look like.

## Cost Components

### 1. Port Handling Cost
- **Formula**: `Cargo (MT) × Port Handling Rate (₹/MT)`
- **Typical Range**: ₹50-200 per MT
- **Impact**: 20-40% of total cost
- **Optimization Potential**: Low (fixed rates)

### 2. Rail Transport Cost
- **Formula**: `Cargo (MT) × Rail Rate (₹/MT) for Port→Plant route`
- **Typical Range**: ₹100-500 per MT (distance-dependent)
- **Impact**: 40-60% of total cost
- **Optimization Potential**: Medium (route selection)

### 3. Demurrage Cost (Vessel Delays)
- **Formula**: `Delay Days × Demurrage Rate × 24 hours`
- **Delay**: `max(0, Actual Berth Time - Expected ETA)`
- **Typical Rate**: ₹10,000-50,000 per day
- **Impact**: 10-40% of total cost (highly variable)
- **Optimization Potential**: **HIGH** (scheduling optimization)

## Baseline vs Optimized Solutions

### Baseline (FCFS - First Come First Served)
- **Method**: Sequential vessel processing, no optimization
- **Characteristics**:
  - Vessels berth in ETA order
  - Port congestion causes cascading delays
  - No consideration of plant proximity or rail costs
  - Typical handling time: 1.5 days per vessel
  - **Higher demurrage costs** due to queuing

### Optimized (MILP/AI)
- **Method**: Mathematical optimization (MILP) or AI algorithms (GA, SA)
- **Characteristics**:
  - Parallel berthing at multiple ports when possible
  - Vessel-plant assignments minimize total cost
  - Rake availability considered
  - Faster handling through better coordination
  - **Lower demurrage costs** through smart scheduling

## Realistic Optimization Savings

### Typical Cost Reduction Ranges

| Scenario | Expected Savings | Primary Source |
|----------|-----------------|----------------|
| **Low Congestion** | 5-15% | Rail route optimization |
| **Medium Congestion** | 15-30% | Demurrage reduction + routes |
| **High Congestion** | 30-50% | Significant demurrage savings |
| **Extreme Cases** | 50-70% | Baseline had major inefficiencies |

### Why 100% Reduction is Impossible
- Port handling costs are unavoidable (fixed rates)
- Rail transport is required (cargo must reach plants)
- Some vessel waiting is inevitable (capacity constraints)
- **Realistic maximum**: ~70-80% in extreme cases with very poor baseline

### Red Flags (Indicating Errors)

⚠️ **Warning Signs**:
- **100% cost reduction**: Baseline cost likely calculated incorrectly (missing demurrage)
- **Negative costs**: Solver error or constraint violation
- **Cost increase**: Over-constrained problem or infeasible solution
- **Zero baseline cost**: Data loading issue

## Cost Calculation Fix (v2.0)

### Previous Issue
The baseline solution was missing **demurrage cost calculations**, making it appear artificially cheap and leading to impossible savings percentages.

### Current Implementation
✅ Baseline now includes:
- Port handling costs
- Rail transport costs
- **Demurrage costs** from vessel queuing and delays

✅ Improved baseline realism:
- Sequential berthing (vessels must wait for port availability)
- Slower handling times (1.5 days vs optimized 0.5-1 day)
- No route optimization
- No parallel processing

## Example Cost Breakdown

### Sample Scenario (10 vessels, 50,000 MT total)

**Baseline FCFS**:
- Port Handling: ₹5,000,000 (₹100/MT)
- Rail Transport: ₹15,000,000 (₹300/MT)
- Demurrage: ₹8,000,000 (avg 4 days delay × ₹20,000/day × 10 vessels)
- **Total: ₹28,000,000**

**Optimized MILP**:
- Port Handling: ₹5,000,000 (same - fixed)
- Rail Transport: ₹13,000,000 (better routes - 13% reduction)
- Demurrage: ₹2,000,000 (smart scheduling - 75% reduction)
- **Total: ₹20,000,000**

**Savings**: ₹8,000,000 (28.6% reduction) ✅ Realistic!

## Validation Checks in UI

The application now includes automatic sanity checks:

1. **Baseline Cost > 0**: Ensures valid baseline calculation
2. **Optimized ≤ Baseline**: Flags if optimization made things worse
3. **Savings < 95%**: Caps display at realistic maximum
4. **Component Breakdown**: Shows port/rail/demurrage split

## Tips for Realistic Results

1. **Run Baseline First**: Always establish a proper baseline before optimization
2. **Check Cost Breakdown**: Review the pie chart to ensure all components are present
3. **Interpret High Savings**: >50% usually means baseline had severe inefficiencies
4. **Scenario Testing**: Use What-If scenarios to test congestion impact
5. **Export Data**: Download CSV to verify individual assignments

## Technical Details

### Demurrage Calculation Code
```python
# In baseline
delay_days = max(0, actual_berth_time - eta)
demurrage_cost = delay_days * demurrage_rate * 24  # Convert to hours

# In MILP
prob += demurrage_cost[v] >= pulp.lpSum([
    demurrage_rate * max(0, t - vessel_eta) * y[v, vessel_port, t]
    for t in time_periods
])
```

### Cost Aggregation
```python
total_cost = port_handling + rail_transport + demurrage
```

All three components are now properly included in both baseline and optimized solutions.

---

**Last Updated**: October 2025  
**Version**: 2.0 (Fixed demurrage calculation)


def calculate_gap(actual, target):
    if target == 0: return 0
    return round((1 + (actual - target) / target) * 100, 1)

print(f"Goal: 100, Actual: 90 -> {calculate_gap(90, 100)}%")
print(f"Goal: 100, Actual: 110 -> {calculate_gap(110, 100)}%")
print(f"Goal: 100, Actual: 100 -> {calculate_gap(100, 100)}%")

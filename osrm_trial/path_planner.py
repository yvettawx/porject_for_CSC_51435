import itertools
import webbrowser
from pathlib import Path

import folium
import osmnx as ox
import networkx as nx

# ---------------------------------------------------------------------------
# Data
# ---------------------------------------------------------------------------

# (latitude, longitude)
START  = (48.8566, 2.3522)   # replace with your actual coordinates
GOALS  = [
    (48.8606, 2.3376),
    (48.8530, 2.3499),
    (48.8490, 2.3620),
]

# ---------------------------------------------------------------------------
# Build street graph covering all points
# ---------------------------------------------------------------------------

def bounding_box(points: list[tuple[float, float]], padding: float = 0.005):
    """Return (north, south, east, west) covering all points with padding."""
    lats = [p[0] for p in points]
    lons = [p[1] for p in points]
    return (
        max(lats) + padding,
        min(lats) - padding,
        max(lons) + padding,
        min(lons) - padding,
    )


def load_graph(points: list[tuple[float, float]]) -> nx.MultiDiGraph:
    north, south, east, west = bounding_box(points)
    print("Downloading street network...")
    # osmnx 2.x takes bbox as a single (left, bottom, right, top) tuple
    G = ox.graph_from_bbox((west, south, east, north), network_type="drive")
    G = ox.add_edge_speeds(G)
    G = ox.add_edge_travel_times(G)
    print(f"Graph loaded: {len(G.nodes)} nodes, {len(G.edges)} edges")
    return G


# ---------------------------------------------------------------------------
# Routing
# ---------------------------------------------------------------------------

def nearest_node(G: nx.MultiDiGraph, lat: float, lon: float) -> int:
    return ox.nearest_nodes(G, lon, lat)  # note: osmnx takes (lon, lat)


def route_distance_m(G: nx.MultiDiGraph, node_a: int, node_b: int) -> float:
    """Shortest path length in meters between two graph nodes."""
    return nx.shortest_path_length(G, node_a, node_b, weight="length")


def route_nodes(G: nx.MultiDiGraph, node_a: int, node_b: int) -> list[int]:
    """Sequence of node IDs for the shortest path between two graph nodes."""
    return nx.shortest_path(G, node_a, node_b, weight="length")


# ---------------------------------------------------------------------------
# TSP over permutations
# ---------------------------------------------------------------------------

def _route_total(G, ordered_nodes):
    """Compute total distance and segments for an ordered list of graph nodes."""
    total = 0.0
    segments = []
    for a, b in zip(ordered_nodes, ordered_nodes[1:]):
        seg = route_nodes(G, a, b)
        total += route_distance_m(G, a, b)
        segments.append(seg if not segments else seg[1:])
    return total, segments


def _nearest_neighbor_order(G, start_node, goal_nodes):
    """Greedy nearest-neighbor heuristic: always visit the closest unvisited goal next."""
    remaining = list(range(len(goal_nodes)))
    order = []
    current = start_node
    while remaining:
        best_i = min(remaining, key=lambda i: route_distance_m(G, current, goal_nodes[i]))
        order.append(best_i)
        current = goal_nodes[best_i]
        remaining.remove(best_i)
    return order


def _two_opt(G, start_node, goal_nodes, order):
    """Improve a visit order by repeatedly applying 2-opt swaps."""
    improved = True
    while improved:
        improved = False
        for i in range(len(order) - 1):
            for j in range(i + 1, len(order)):
                new_order = order[:i] + order[i:j + 1][::-1] + order[j + 1:]
                ordered_old = [start_node] + [goal_nodes[k] for k in order]
                ordered_new = [start_node] + [goal_nodes[k] for k in new_order]
                try:
                    old_dist, _ = _route_total(G, ordered_old)
                    new_dist, _ = _route_total(G, ordered_new)
                except nx.NetworkXNoPath:
                    continue
                if new_dist < old_dist:
                    order = new_order
                    improved = True
                    break
            if improved:
                break
    return order


def best_visit_order(
    G: nx.MultiDiGraph,
    start: tuple[float, float],
    goals: list[tuple[float, float]],
) -> tuple[list[tuple[float, float]], float, list[int]]:
    """
    Find a good visit order for goals starting from start.

    - <= 8 goals: exact solution via brute-force permutation
    - > 8 goals: nearest-neighbor heuristic + 2-opt refinement
    """
    all_points = [start] + goals
    nodes = {pt: nearest_node(G, pt[0], pt[1]) for pt in all_points}

    start_node = nodes[start]
    goal_nodes = [nodes[g] for g in goals]

    if len(goals) <= 8:
        # Exact brute-force
        best_order = None
        best_dist = float("inf")
        best_segments = None

        for perm in itertools.permutations(range(len(goals))):
            ordered_nodes = [start_node] + [goal_nodes[i] for i in perm]
            try:
                total, segments = _route_total(G, ordered_nodes)
            except nx.NetworkXNoPath:
                continue
            if total < best_dist:
                best_dist = total
                best_order = [goals[i] for i in perm]
                best_segments = segments
    else:
        # Heuristic: nearest-neighbor + 2-opt
        try:
            order_indices = _nearest_neighbor_order(G, start_node, goal_nodes)
            order_indices = _two_opt(G, start_node, goal_nodes, order_indices)
            ordered_nodes = [start_node] + [goal_nodes[i] for i in order_indices]
            best_dist, best_segments = _route_total(G, ordered_nodes)
            best_order = [goals[i] for i in order_indices]
        except nx.NetworkXNoPath:
            best_segments = None

    if best_segments is None:
        raise ValueError("No path found between points.")
    full_path = [node for seg in best_segments for node in seg]
    return best_order, best_dist, full_path


# ---------------------------------------------------------------------------
# Visualization
# ---------------------------------------------------------------------------

def plot_route(
    G: nx.MultiDiGraph,
    start: tuple[float, float],
    goals: list[tuple[float, float]],
    visit_order: list[tuple[float, float]],
    path_nodes: list[int],
    output_path: str = "route_map.html",
) -> None:
    """
    Render the route on an interactive Folium map and open it in the browser.

    - Blue marker   : start point
    - Red markers   : goal points (numbered in visit order)
    - Blue polyline : the full road-snapped route
    """
    center_lat = (start[0] + sum(g[0] for g in goals)) / (1 + len(goals))
    center_lon = (start[1] + sum(g[1] for g in goals)) / (1 + len(goals))
    m = folium.Map(location=[center_lat, center_lon], zoom_start=14, tiles="OpenStreetMap")

    # --- route polyline (road-snapped) ---
    coords = [(G.nodes[n]["y"], G.nodes[n]["x"]) for n in path_nodes]
    folium.PolyLine(coords, color="royalblue", weight=5, opacity=0.8, tooltip="Route").add_to(m)

    # --- start marker ---
    folium.Marker(
        location=start,
        tooltip="Start",
        icon=folium.Icon(color="blue", icon="play", prefix="fa"),
    ).add_to(m)

    # --- goal markers in visit order ---
    for i, goal in enumerate(visit_order, 1):
        folium.Marker(
            location=goal,
            tooltip=f"Goal {i}",
            icon=folium.Icon(color="red", icon=str(i), prefix="fa"),
        ).add_to(m)

    out = Path(output_path).resolve()
    m.save(str(out))
    print(f"\nMap saved to {out}")
    webbrowser.open(out.as_uri())


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    all_points = [START] + GOALS
    G = load_graph(all_points)

    order, dist, path = best_visit_order(G, START, GOALS)

    print(f"\nBest visit order (total {dist/1000:.2f} km):")
    print(f"  Start  -> {START}")
    for i, goal in enumerate(order, 1):
        print(f"  Goal {i} -> {goal}")

    print(f"\nFull path: {len(path)} nodes")

    plot_route(G, START, GOALS, order, path)

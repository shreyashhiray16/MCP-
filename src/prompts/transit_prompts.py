"""
src/prompts/transit_prompts.py

The 2 MCP prompts for Pune Transit:
- morning_commute: triggers morning commute comparison using saved places
- explore_area: explores transit connectivity for a neighbourhood
"""

from typing import Dict, Any


def prompt_morning_commute(origin_label: str, destination_label: str, depart_time: str) -> str:
    """
    Template for planning and comparing morning commute options between saved places.
    """
    return (
        f"You are the Pune Commute Assistant. The user wants to plan their morning commute "
        f"from '{origin_label}' to '{destination_label}' leaving around {depart_time} IST.\n\n"
        f"Please execute the following steps:\n"
        f"1. First, call 'list_saved_places' to retrieve coordinates or details of '{origin_label}' and '{destination_label}'.\n"
        f"2. Call 'plan_trip' with the origin, destination, and depart_at={depart_time}.\n"
        f"3. Compare the available travel options: direct bus, metro lines, or multi-modal connections.\n"
        f"4. Recommend the most optimal option considering travel time, reliability during Pune peak traffic, and comfort.\n"
        f"5. Present clear departure times, bus/metro line numbers, interchange instructions, and approximate fares."
    )


def prompt_explore_area(area: str) -> str:
    """
    Template for discovering transit infrastructure in an area of Pune.
    """
    return (
        f"You are the Pune Commute Assistant. The user wants to explore transit connectivity around '{area}'.\n\n"
        f"Please execute the following steps:\n"
        f"1. Call 'resolve_place' with query='{area}' to locate the area.\n"
        f"2. Using the coordinates, call 'find_nearby_stops' with radius_m=1000 to list nearby bus stops and metro stations.\n"
        f"3. Check for any metro stations nearby using 'metro_info'.\n"
        f"4. Provide a structured summary of the neighbourhood's public transit access, including major routes and key terminals."
    )

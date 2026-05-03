"""
Date and Time Parser for Spanish natural language expressions.
Handles expressions like "mañana", "el martes", "a las 15hs", "por la tarde", etc.
"""
from datetime import datetime, timedelta, timezone as tz
from typing import Optional, Tuple
from loguru import logger


def parse_spanish_date(date_str: str) -> Optional[datetime]:
    """
    Parse Spanish date expressions.
    
    Supported:
    - "hoy", "mañana", "pasado mañana"
    - "el lunes", "el martes", etc.
    - "próximo lunes", "próximo viernes"
    - "2026-04-25", "25/04/2026"
    - days of week: 0=monday, 6=sunday
    
    Returns datetime with timezone UTC
    """
    if not date_str:
        return None
    
    date_str_lower = date_str.lower().strip()
    today = datetime.now(tz.utc)
    
    try:
        # Try direct parse first
        return datetime.strptime(date_str, "%Y-%m-%d").replace(tzinfo=tz.utc)
    except ValueError:
        pass
    
    try:
        # Try DD/MM/YYYY
        dt = datetime.strptime(date_str.replace("-", "/"), "%d/%m/%Y")
        return dt.replace(tzinfo=tz.utc)
    except ValueError:
        pass
    
    # Handle relative dates
    if date_str_lower == "hoy":
        return today.replace(hour=10, minute=0, second=0)
    
    if date_str_lower == "mañana":
        tomorrow = today + timedelta(days=1)
        return tomorrow.replace(hour=10, minute=0, second=0)
    
    if date_str_lower == "pasado mañana" or "pasado mañana" in date_str_lower:
        day_after = today + timedelta(days=2)
        return day_after.replace(hour=10, minute=0, second=0)
    
    # Handle day of week
    days_map = {
        "lunes": 0, "martes": 1, "miercoles": 2, "miércoles": 2,
        "jueves": 3, "viernes": 4, "sabado": 5, "sábado": 5, "domingo": 6
    }
    
    for day_name, day_num in days_map.items():
        if day_name in date_str_lower or f"el {day_name}" in date_str_lower:
            days_ahead = day_num - today.weekday()
            if days_ahead <= 0:
                days_ahead += 7
            
            target_date = today + timedelta(days=days_ahead)
            return target_date.replace(hour=10, minute=0, second=0)
    
    # Handle "próximo" + day
    if "próximo" in date_str_lower or "proximo" in date_str_lower:
        for day_name, day_num in days_map.items():
            if day_name in date_str_lower:
                days_ahead = day_num - today.weekday()
                if days_ahead <= 0:
                    days_ahead += 7
                if "próximo" in date_str_lower or "proximo" in date_str_lower:
                    days_ahead += 7
                
                target_date = today + timedelta(days=days_ahead)
                return target_date.replace(hour=10, minute=0, second=0)
    
    logger.warning(f"[DateParser] Could not parse date: {date_str}")
    return None


def parse_spanish_time(time_str: str) -> Optional[Tuple[int, int]]:
    """
    Parse Spanish time expressions.
    
    Supported:
    - "15:00", "16:30"
    - "15hs", "3pm", "3 pm"
    - "a las 15hs", "a las 3"
    - "por la mañana", "mañana" -> 10:00
    - "por la tarde", "tarde" -> 15:00-17:00
    - "después del mediodía", "mediodía" -> 12:00
    - "10", "11", "12" -> hour
    
    Returns (hour, minute) tuple
    """
    if not time_str:
        return (10, 0)  # Default to 10:00
    
    time_str_lower = time_str.lower().strip()
    
    # Handle empty
    if time_str_lower in ("", "sin especificar", "no especificado"):
        return (10, 0)
    
    # Try direct time format
    try:
        return datetime.strptime(time_str_lower, "%H:%M").time().hour, 0
    except ValueError:
        pass
    
    # Try hour only
    try:
        hour = int(time_str_lower)
        if 0 <= hour <= 23:
            return hour, 0
    except ValueError:
        pass
    
    # Handle "a las Xhs" or "a las X"
    if "a las" in time_str_lower or "las" in time_str_lower:
        import re
        numbers = re.findall(r'\d+', time_str_lower)
        if numbers:
            hour = int(numbers[0])
            if "pm" in time_str_lower and hour < 12:
                hour += 12
            if "am" in time_str_lower and hour == 12:
                hour = 0
            if 0 <= hour <= 23:
                return hour, 0
    
    # Handle "3pm", "3 pm"
    import re
    numbers = re.findall(r'\d+', time_str_lower)
    if numbers:
        hour = int(numbers[0])
        if "pm" in time_str_lower and hour < 12:
            hour += 12
        if "am" in time_str_lower and hour == 12:
            hour = 0
        if 0 <= hour <= 23:
            return hour, 0
    
    # Handle time of day expressions
    if "mañana" in time_str_lower or "por la mañana" in time_str_lower:
        return (10, 0)  # 10:00
    
    if "tarde" in time_str_lower and "a la" not in time_str_lower:
        return (15, 0)  # 15:00
    
    if "mediodia" in time_str_lower or "mediodía" in time_str_lower:
        return (12, 0)  # 12:00
    
    if "noche" in time_str_lower:
        return (19, 0)  # 19:00
    
    # Handle "10 de la mañana", "3 de la tarde"
    if "de la" in time_str_lower:
        numbers = re.findall(r'\d+', time_str_lower)
        if numbers:
            hour = int(numbers[0])
            if "tarde" in time_str_lower and hour < 12:
                hour += 12
            if "mañana" in time_str_lower:
                hour = hour if 9 <= hour <= 12 else 10
            if 0 <= hour <= 23:
                return hour, 0
    
    logger.warning(f"[DateParser] Could not parse time: {time_str}")
    return (10, 0)


def combine_date_time(date_input: str, time_input: Optional[str]) -> Tuple[datetime, bool]:
    """
    Combine parsed date and time into a single datetime.
    
    Args:
        date_input: Date string from user
        time_input: Optional time string from user
    
    Returns:
        (datetime, success: bool)
    """
    parsed_date = parse_spanish_date(date_input)
    if not parsed_date:
        return datetime.now(tz.utc), False
    
    if time_input:
        hour, minute = parse_spanish_time(time_input)
    else:
        hour, minute = 10, 0  # Default
    
    final_dt = parsed_date.replace(hour=hour, minute=minute, second=0)
    
    # Validate it's in the future
    now = datetime.now(tz.utc)
    if final_dt < now:
        # Try next week if past
        final_dt += timedelta(days=7)
    
    return final_dt, True


# Quick test
if __name__ == "__main__":
    test_cases = [
        ("mañana", "15:00"),
        ("el martes", "a las 3 de la tarde"),
        ("viernes", "10am"),
        ("2026-04-25", "16:30"),
        ("próximo jueves", None),
        ("hoy", "por la tarde"),
    ]
    
    print("Testing date/time parser:")
    for date_input, time_input in test_cases:
        dt, success = combine_date_time(date_input, time_input)
        print(f"  {date_input} + {time_input} -> {dt.strftime('%Y-%m-%d %H:%M')} (success: {success})")
"""
Robust Date-Time Parser for InmuebleBot.
Handles Spanish natural language expressions with Argentine timezone (UTC-3).

Supports:
- Relative: "mañana", "pasado mañana", "hoy", "esta noche"
- Weekdays: "el lunes", "el martes que viene", "el próximo lunes", "este lunes", "lunes que viene"
- Week: "esta semana", "la próxima semana", "la semana que viene", "dentro de una semana"
- Weekend: "este fin de semana", "el fin de semana"
- Time periods: "por la mañana", "por la tarde", "por la noche", "al mediodía", "esta tarde", "a primera hora"
- Combined: "el lunes que viene a las 4pm", "mañana a las 10 de la mañana", "este sábado al mediodía"
- Numeric: "el 5 de mayo", "29/04/2026"
- Vague (returns error): "pronto", "en unos días"
"""
from datetime import datetime, timedelta, date
from typing import Optional, Tuple
import re
import pytz
from loguru import logger

ARG_TZ = pytz.timezone('America/Argentina/Buenos_Aires')
DEFAULT_VISIT_DURATION = timedelta(hours=1)


def get_argentina_now() -> datetime:
    return datetime.now(ARG_TZ)



def _parse_date_advanced(user_text: str, now: datetime) -> Tuple[Optional[datetime], Optional[str]]:
    """Advanced date parsing for Spanish expressions."""
    
    # === Try direct numeric formats first ===
    for fmt in ["%d/%m/%Y", "%Y-%m-%d", "%d/%m/%y"]:
        try:
            dt = datetime.strptime(user_text, fmt)
            if fmt == "%d/%m/%y" and dt.year < now.year:
                dt = dt.replace(year=now.year + 1)
            return dt.replace(hour=10, minute=0, second=0), None
        except ValueError:
            continue
    
    # === Month mapping ===
    month_map = {
        "enero": 1, "febrero": 2, "marzo": 3, "abril": 4, "mayo": 5, "junio": 6,
        "julio": 7, "agosto": 8, "septiembre": 9, "octubre": 10, "noviembre": 11, "diciembre": 12
    }
    
    # === "el 25 de abril" or "25 de abril" ===
    match = re.search(r'(\d{1,2})\s+(?:de|del)\s+(\w+)(?:\s+de\s+(\d{4}))?', user_text)
    if match:
        day = int(match.group(1))
        month_name = match.group(2).lower()
        if month_name in month_map:
            month = month_map[month_name]
            year = int(match.group(3)) if match.group(3) else now.year
            if year < now.year:
                year += 1
            try:
                return datetime(year, month, day, 10, 0), None
            except ValueError:
                return datetime(year + 1, month, day, 10, 0), None
        elif month_name in ("este", "éste", "corriente", "próximo", "proximo", "siguiente"):
            # "17 de este mes" = this month, day 17
            month = now.month
            year = now.year
            try:
                dt = datetime(year, month, day, 10, 0)
                if dt.date() < now.date():
                    dt = dt.replace(month=month + 1) if month < 12 else dt.replace(year=year + 1, month=1)
                return dt, None
            except ValueError:
                pass
    
    # === "el 17" (standalone day of month, defaults to current month) ===
    match = re.search(r'^el\s+(?:d[ií]a\s+)?(\d{1,2})\s*(?:de\s+este|del?\s+corriente)?$', user_text)
    if match:
        day = int(match.group(1))
        if 1 <= day <= 31:
            try:
                dt = datetime(now.year, now.month, day, 10, 0)
                if dt.date() < now.date():
                    dt = dt.replace(month=now.month + 1) if now.month < 12 else dt.replace(year=now.year + 1, month=1)
                return dt, None
            except ValueError:
                pass

    # === VAGUE expressions - ask for clarification ===
    vague_terms = ["pronto", "en unos días", "en unos dias", "la semana entrante", "próximamente"]

    for term in vague_terms:
        if term in user_text:
            return None, f"La expresión '{term}' es muy ambigua. ¿Podrías darme una fecha más específica?"
    
    # === Simple relative dates with default times ===
    # "hoy" -> today at 10:00
    if user_text in ("hoy", "today"):
        return now.replace(hour=10, minute=0, second=0), None
    
    # "mañana" -> tomorrow at 10:00
    if user_text in ("mañana", "amanana", "manana", "tomorrow"):
        tomorrow = now + timedelta(days=1)
        return tomorrow.replace(hour=10, minute=0, second=0), None
    
    # "pasado mañana" -> day after tomorrow at 10:00
    if "pasado mañana" in user_text or user_text == "pasado":
        day_after = now + timedelta(days=2)
        return day_after.replace(hour=10, minute=0, second=0), None
    
    # === "esta semana" - this week, assume Friday at 10:00 ===
    if "esta semana" in user_text and "próxima" not in user_text and "que viene" not in user_text:
        days_until_friday = (4 - now.weekday()) % 7
        if days_until_friday == 0 and now.hour > 18:
            days_until_friday = 7
        target = now + timedelta(days=days_until_friday)
        return target.replace(hour=10, minute=0, second=0), None
    
    # === "la próxima semana" / "la semana que viene" / "dentro de una semana" ===
    if "próxima" in user_text or "proxima" in user_text or "que viene" in user_text or "dentro de una semana" in user_text:
        days_ahead = 7 + (4 - now.weekday()) % 7
        target = now + timedelta(days=days_ahead)
        return target.replace(hour=10, minute=0, second=0), None
    
    # === "este fin de semana" / "el fin de semana" - this Saturday or next ===
    if "fin de semana" in user_text or "fin de sema" in user_text:
        days_until_sat = (5 - now.weekday()) % 7
        if days_until_sat == 0 and now.hour > 12:
            days_until_sat = 7
        target = now + timedelta(days=days_until_sat)
        return target.replace(hour=10, minute=0, second=0), None
    
    # === Relative days ===
    # "dentro de 4 días", "dentro de una semana", "en 3 días" — relative from now
    import re as _re
    dentro_match = _re.search(r'(?:dentro\s+de|en)\s+(\d+)\s*(?:d[ií]as?|d[ií]a)', user_text)
    if dentro_match:
        days_ahead = int(dentro_match.group(1))
        if 1 <= days_ahead <= 30:
            target = now + timedelta(days=days_ahead)
            return target.replace(hour=10, minute=0, second=0), None

    if user_text in ("hoy", "today"):
        return now.replace(hour=10, minute=0, second=0), None
    
    if user_text in ("mañana", "amanana", "manana", "tomorrow"):
        tomorrow = now + timedelta(days=1)
        return tomorrow.replace(hour=10, minute=0, second=0), None
    
    if "pasado mañana" in user_text or user_text == "pasado":
        day_after = now + timedelta(days=2)
        return day_after.replace(hour=10, minute=0, second=0), None
    
    # === Day of week with modifiers ===
    # Check for "lunes que viene", "el próximo lunes", "este lunes", "el lunes próximo"
    dow_map = {
        "lunes": 0, "martes": 1, "miércoles": 2, "miercoles": 2,
        "jueves": 3, "viernes": 4, "sábado": 5, "sabado": 5, "domingo": 6
    }
    weekday_patterns = [
        (r'el?\s*(\w+)\s+que\s+viene', 1),  # "lunes que viene" = next occurrence
        (r'el?\s*próximo\s+(\w+)', 1),    # "el próximo lunes" = next occurrence  
        (r'el?\s*proximo\s+(\w+)', 1),   # "el proximo lunes"
        (r'este\s+(\w+)', 0),           # "este lunes" = this week if not passed
    ]
    
    for pattern, week_offset in weekday_patterns:
        match = re.search(pattern, user_text)
        if match:
            day_name = match.group(1).lower()
            if day_name in dow_map:
                target_dow = dow_map[day_name]
                current_dow = now.weekday()
                days_ahead = target_dow - current_dow
                if days_ahead <= 0:
                    days_ahead += (7 * (week_offset + 1))
                elif week_offset > 0:
                    days_ahead += (7 * week_offset)
                target = now + timedelta(days=days_ahead)
                return target.replace(hour=10, minute=0, second=0), None
    
    # Simple weekday fallback (no modifier) - checked AFTER weekday_patterns for priority
    for day_name, target_dow in dow_map.items():
        if day_name in user_text or f"el {day_name}" in user_text:
            current_dow = now.weekday()
            days_ahead = target_dow - current_dow
            if days_ahead <= 0:
                days_ahead += 7
            target = now + timedelta(days=days_ahead)
            return target.replace(hour=10, minute=0, second=0), None
    
    return None, None


def _parse_time_advanced(user_text: str) -> Tuple[Optional[int], Optional[int]]:
    """Advanced time parsing for Spanish expressions."""
    if not user_text:
        return None, None
    
    user_text = user_text.strip().lower()
    
    # === 24-hour format: "15:00", "16:30" ===
    match = re.search(r'(\d{1,2}):(\d{2})', user_text)
    if match:
        hour, minute = int(match.group(1)), int(match.group(2))
        if 0 <= hour <= 23 and 0 <= minute <= 59:
            return hour, minute
    
    # === Hour only: "15hs", "a las 15", "las 15" ===
    match = re.search(r'(?:^|a\s+)?las?\s*(\d{1,2})\s*hs?\s*$', user_text)
    if match:
        hour = int(match.group(1))
        if 0 <= hour <= 23:
            return hour, 0
    
    # === AM/PM: "6pm", "10am" ===
    match = re.search(r'(\d{1,2})\s*(am|pm)', user_text)
    if match:
        hour = int(match.group(1))
        ampm = match.group(2)
        if ampm == "pm" and hour < 12:
            hour += 12
        elif ampm == "am" and hour == 12:
            hour = 0
        if 0 <= hour <= 23:
            return hour, 0
    
    # === "a las X de la mañana" / "a las X de la tarde" ===
    match = re.search(r'a\s*las?\s*(\d{1,2})\s*de\s*la\s*(mañana|tarde|noche)', user_text)
    if match:
        hour = int(match.group(1))
        period = match.group(2)
        if period == "tarde" and hour < 12:
            hour += 12
        elif period == "noche" and hour < 12:
            hour += 12
        if 0 <= hour <= 23:
            return hour, 0

    # "X de la mañana/tarde/noche" (sin "a las") — ej: "11 de la mañana", "3 de la tarde"
    match = re.search(r'(\d{1,2})\s+de\s+la\s+(mañana|tarde|noche)', user_text)
    if match:
        hour = int(match.group(1))
        period = match.group(2)
        if period in ("tarde", "noche") and hour < 12:
            hour += 12
        if 0 <= hour <= 23:
            return hour, 0

    # === Time periods ===
    if re.search(r'(?:por|a)\s*la\s*mañana', user_text):
        return 10, 0
    if re.search(r'(?:por|a)\s*la\s*tarde', user_text):
        return 15, 0
    if re.search(r'(?:por|a)\s*la\s*noche', user_text):
        return 20, 0
    if "mediod" in user_text or "mediodía" in user_text:
        return 12, 0
    if "primera hora" in user_text:
        return 9, 0
    
    # === "esta tarde" / "esta noche" - current day afternoon/evening ===
    if "esta noche" in user_text:
        return 20, 0
    if "esta tarde" in user_text:
        if get_argentina_now().hour < 15:
            return 15, 0
        return 16, 0
    
    return None, None


def _split_date_time(user_text: str) -> Tuple[Optional[str], Optional[str]]:
    """Split combined date+time input into separate date and time strings.
    
    Only splits for NUMERIC date formats like "29/04/2026 18:00".
    Does NOT split for natural language like "mañana a las 15hs".
    
    Handles formats like:
    - "29/04/2026 18:00" -> date="29/04/2026", time="18:00"
    - "29/04/2026 a las 18:00" -> date="29/04/2026", time="18:00"
    - "29/04/2026 6pm" -> date="29/04/2026", time="6pm"
    - "29/04/2026" -> date="29/04/2026", time=None
    - "mañana a las 15hs" -> NOT split (returns as-is)
    """
    user_text = user_text.strip()
    
    # Pattern to find time-like patterns at the end
    # Matches: "18:00", "6pm", "18hs", "a las 18", "a las 18:00", "a las 6pm"
    time_patterns = [
        r'(\d{1,2}):(\d{2})\s*$',  # 18:00
        r'(\d{1,2})\s*pm\s*$',      # 6pm, 18pm
        r'(\d{1,2})\s*am\s*$',      # 6am
        r'(\d{1,2})\s*hs?\s*$',     # 18hs, 18h
        r'a\s+las\s+(\d{1,2})(?::(\d{2}))?\s*$',  # a las 18, a las 18:30
    ]
    
    for pattern in time_patterns:
        match = re.search(pattern, user_text)
        if match:
            date_part = user_text[:match.start()].strip()
            time_part = match.group(0).strip()
            
            # Only split if date part looks numeric (contains digits and / or -)
            # This prevents splitting natural language like "mañana a las 15hs"
            if not re.search(r'\d', date_part) or ('/' not in date_part and '-' not in date_part):
                # Not a numeric date format - don't split
                return user_text, None
            
            # Clean up date part - remove "el " prefix if present
            if date_part.startswith('el '):
                date_part = date_part[3:]
            
            # Clean up time part
            time_part = time_part.replace('a las ', '').replace('a las', '')
            
            return date_part, time_part
    
    # No time found - return date only
    return user_text, None


def _try_parse_combined(user_text: str, now: datetime) -> Tuple[Optional[datetime], Optional[str]]:
    """Try to extract date + time from combined input like 'mañana a las 15hs' or '29/04/2026 18:00'."""
    
    # === First: Try to split numeric date+time (most reliable for "DD/MM/YYYY HH:MM") ===
    # This handles "29/04/2026 18:00", "29/04/2026 a las 18", etc.
    date_str, time_str = _split_date_time(user_text)
    
    logger.info(f"[DateParser] Split result for '{user_text}': date='{date_str}', time='{time_str}'")
    
    if date_str and date_str != user_text:
        # Try numeric date formats first (DD/MM/YYYY, etc.)
        for fmt in ["%d/%m/%Y", "%Y-%m-%d", "%d/%m/%y"]:
            try:
                parsed_date = datetime.strptime(date_str, fmt)
                
                # If date is still naive (no timezone), add one
                if parsed_date.tzinfo is None:
                    parsed_date = ARG_TZ.localize(parsed_date)
                else:
                    parsed_date = parsed_date.astimezone(ARG_TZ)
                
                # Apply year if using short format
                if fmt == "%d/%m/%y" and parsed_date.year < now.year:
                    parsed_date = parsed_date.replace(year=now.year + 1)
                
                # Now parse time if available
                if time_str:
                    parsed_time = _parse_time(time_str)
                    if parsed_time:
                        dt = parsed_date.replace(
                            hour=parsed_time[0], 
                            minute=parsed_time[1], 
                            second=0
                        )
                        logger.info(f"[DateParser] Numeric date+time success: '{date_str}' + '{time_str}' = {dt.isoformat()}")
                        return dt, None
                    else:
                        # Time ambiguous - return error so main function asks for time
                        logger.info(f"[DateParser] Date parsed but time ambiguous: '{time_str}'")
                        return None, "¿A qué hora te gustaría la visita? Dime algo como 'a las 10', '15:00', o 'por la tarde'"
                else:
                    # No time provided - return error so main function asks for time  
                    logger.info(f"[DateParser] Date parsed but no time: '{date_str}'")
                    return None, "¿A qué hora te gustaría la visita? Dime algo como 'a las 10', '15:00', o 'por la tarde'"
            except ValueError as e:
                logger.info(f"[DateParser] strptime failed for '{date_str}' with {fmt}: {e}")
                continue
        # End of numeric date format trying
        
        # If we get here, date_str was set but couldn't parse as numeric date
        # Fall through to phrase-based parsing
    
    # === Original logic: Try phrase-based parsing ===
    # First try direct: find date phrase, then look for time in remaining text
    possible_date_phrases = [
        'hoy', 'mañana', 'manana', 'amanana', 'pasado mañana', 'pasado',
        'lunes', 'martes', 'miércoles', 'miercoles', 'jueves', 'viernes', 'sábado', 'sabado', 'domingo',
        'este lunes', 'este martes', 'este miércoles', 'este jueves', 'este viernes',
        'próximo lunes', 'próximo martes', 'próximo miércoles', 'próximo jueves', 'próximo viernes',
    ]
    
    date_phrase = None
    for phrase in possible_date_phrases:
        if phrase in user_text:
            date_phrase = phrase
            
            # Find what comes after the date phrase - that's the time
            remaining = user_text[user_text.find(phrase) + len(phrase):].strip()
            
            if remaining:
                # There's something after the date - it should be time
                parsed_date = _parse_date(phrase, now)
                if parsed_date:
                    parsed_time = _parse_time(remaining)
                    if parsed_time:
                        dt = parsed_date.replace(hour=parsed_time[0], minute=parsed_time[1], second=0)
                        if dt.tzinfo is None:
                            dt = ARG_TZ.localize(dt)
                        else:
                            dt = dt.astimezone(ARG_TZ)
                        
                        logger.info(f"[DateParser] Combined parse: '{phrase}' + '{remaining}' = {dt.isoformat()}")
                        return dt, None
            
            break
    
    # Try date with numbers like "el 28 de abril"
    for phrase in ['el ', ' de ']:
        idx = user_text.find(phrase)
        if idx >= 0:
            parsed_date = _parse_date(user_text, now)
            if parsed_date:
                remaining = user_text[idx + len(phrase):].strip()
                parsed_time = _parse_time(remaining) if remaining else None
                
                if parsed_time:
                    dt = parsed_date.replace(hour=parsed_time[0], minute=parsed_time[1], second=0)
                    if dt.tzinfo is None:
                        dt = ARG_TZ.localize(dt)
                    else:
                        dt = dt.astimezone(ARG_TZ)
                    return dt, None
    
    return None, None


def parse_spanish_datetime(user_text: str) -> Tuple[Optional[datetime], Optional[str]]:
    """
    Parse Spanish date/time expressions into timezone-aware datetime.
    Supports broad range of Spanish natural language expressions.
    
    Args:
        user_text: The raw user input string
        
    Returns:
        Tuple of (parsed_datetime, error_message)
    """
    if not user_text:
        return None, "No proporcionaste ninguna fecha"
    
    original_input = user_text
    user_text = user_text.lower().strip()
    now = get_argentina_now()
    
    logger.info(f"[DateParser] Parsing: '{original_input}'")
    
    # === 1. Try numeric date + time first ===
    result, error = _try_parse_combined(user_text, now)
    if result is not None:
        return result, error
    
    # === 2. Try advanced date parsing with time extraction ===
    # Split date and time from combined expressions
    date_part, time_part = _extract_date_time_parts(user_text)
    
    if date_part:
        parsed_date, date_error = _parse_date_advanced(date_part, now)
        if parsed_date and not date_error:
            # Try to extract time from the full text
            extracted_time = _extract_time_from_text(user_text)
            
            if extracted_time and extracted_time[0] is not None:
                dt = parsed_date.replace(hour=extracted_time[0], minute=extracted_time[1], second=0)
                dt = ARG_TZ.localize(dt) if dt.tzinfo is None else dt.astimezone(ARG_TZ)
                logger.info(f"[DateParser] SUCCESS: '{original_input}' -> {dt.isoformat()}")
                return dt, None
            elif time_part:
                # Time was extracted separately
                parsed_time = _parse_time_advanced(time_part)
                if parsed_time and parsed_time[0] is not None:
                    dt = parsed_date.replace(hour=parsed_time[0], minute=parsed_time[1], second=0)
                    dt = ARG_TZ.localize(dt) if dt.tzinfo is None else dt.astimezone(ARG_TZ)
                    logger.info(f"[DateParser] SUCCESS: '{original_input}' -> {dt.isoformat()}")
                    return dt, None
            
            # Date found but time ambiguous
            return None, "¿A qué hora te gustaría la visita? Dime algo como 'a las 10', '15:00', o 'por la tarde'"
    
    # === 3. Full advanced parsing ===
    parsed_date, date_error = _parse_date_advanced(user_text, now)
    if parsed_date and not date_error:
        extracted_time = _extract_time_from_text(user_text)
        
        if extracted_time and extracted_time[0] is not None:
            dt = parsed_date.replace(hour=extracted_time[0], minute=extracted_time[1], second=0)
            dt = ARG_TZ.localize(dt) if dt.tzinfo is None else dt.astimezone(ARG_TZ)
            logger.info(f"[DateParser] SUCCESS: '{original_input}' -> {dt.isoformat()}")
            return dt, None
        else:
            # Date found but no time - return error asking for time
            return None, "¿A qué hora te gustaría la visita? Dime algo como 'a las 10', '15:00', o 'por la tarde'"
    
    # === 4. Return specific error if parse_date_advanced returned one ===
    if date_error:
        return None, date_error
    
    # === 5. Complete failure ===
    return None, f"No pude entender la fecha '{original_input}'. Usa formato como '28/04/2026' o 'mañana a las 15'"


def _extract_date_time_parts(user_text: str) -> Tuple[Optional[str], Optional[str]]:
    """Extract date and time parts from combined Spanish expression."""
    # Remove common prefixes
    text = user_text.lower().strip()
    
    # Remove time-related words to isolate date
    time_indicators = ['a las', 'por la', 'al mediodía', 'a las', 'en punto', 'pm', 'am', 'hs']
    date_part = text
    time_part = None
    
    for indicator in time_indicators:
        if indicator in text:
            parts = text.split(indicator, 1)
            if parts[0].strip():
                date_part = parts[0].strip()
                if len(parts) > 1:
                    time_part = parts[1].strip()
            break
    
    return date_part, time_part


def _extract_time_from_text(user_text: str) -> Optional[Tuple[int]]:
    """Extract time from full text."""
    text = user_text.lower()
    
    patterns = [
        r'(\d{1,2}):(\d{2})',                               # 15:30
        r'a\s*las?\s*(\d{1,2})(?::(\d{2}))?',               # a las 15, a las 15:30
        r'(\d{1,2})\s*(am|pm)',                              # 3pm, 10am
        r'(\d{1,2})\s*hs',                                   # 15hs
        r'(\d{1,2})\s+de\s+la\s+(?:mañana|tarde|noche)',    # 11 de la mañana
    ]
    
    for pattern in patterns:
        match = re.search(pattern, text)
        if match:
            result = _parse_time_advanced(match.group(0))
            if result:
                return result
    
    # Check for time periods — only fire when there is NO digit in the text.
    # If there IS a digit (e.g. "a las 9 de la mañana"), the regex loop above already
    # extracted the correct hour, so falling through here would overwrite it with a
    # hardcoded default like 10:00.
    if not re.search(r'\d', text):
        if 'mañana' in text and ('de la' in text or 'por la' in text):
            return 10, 0
        if 'tarde' in text and ('de la' in text or 'por la' in text):
            return 15, 0
        if 'noche' in text and ('de la' in text or 'por la' in text):
            return 20, 0
        if 'mediod' in text or 'mediodía' in text:
            return 12, 0

    return None

def _parse_date(user_text: str, now: datetime) -> Optional[datetime]:
    """Parse date part of user input."""
    
    # === Try direct date formats first ===
    # Format: DD/MM/YYYY or YYYY-MM-DD
    for fmt in ["%d/%m/%Y", "%Y-%m-%d", "%d/%m/%y"]:
        try:
            return datetime.strptime(user_text, fmt)
        except ValueError:
            continue
    
    # Try extracting date from "el 25 de abril" format
    month_map = {
        "enero": 1, "febrero": 2, "marzo": 3, "abril": 4, "mayo": 5, "junio": 6,
        "julio": 7, "agosto": 8, "septiembre": 9, "octubre": 10, "noviembre": 11, "diciembre": 12
    }
    
    # Match "el 25 de abril" or "25 de abril"
    match = re.search(r'(\d{1,2})\s+(?:de|del)\s+(\w+)', user_text)
    if match:
        day = int(match.group(1))
        month_name = match.group(2).lower()
        if month_name in month_map:
            month = month_map[month_name]
            year = now.year
            # If date is in past, assume next year
            try:
                dt = datetime(year, month, day, 10, 0)  # Default to 10:00
            except ValueError:
                dt = datetime(year + 1, month, day, 10, 0)
            return dt
        elif month_name in ("este", "éste", "corriente", "próximo", "proximo", "siguiente"):
            # "17 de este mes" = this month, day 17
            month = now.month
            year = now.year
            try:
                dt = datetime(year, month, day, 10, 0)
                if dt.date() < now.date():
                    if month < 12:
                        dt = dt.replace(month=month + 1)
                    else:
                        dt = dt.replace(year=year + 1, month=1)
                return dt
            except ValueError:
                pass
    
    # === Relative dates ===
    if user_text in ("hoy", "today"):
        return now.replace(hour=10, minute=0, second=0)
    
    if user_text in ("mañana", "amanana", "manana", "tomorrow"):
        tomorrow = now + timedelta(days=1)
        return tomorrow.replace(hour=10, minute=0, second=0)
    
    if "pasado mañana" in user_text or user_text == "pasado":
        day_after = now + timedelta(days=2)
        return day_after.replace(hour=10, minute=0, second=0)
    
    # === Day of week ===
    dow_map = {
        "lunes": 0, "martes": 1, "miércoles": 2, "miercoles": 2,
        "jueves": 3, "viernes": 4, "sábado": 5, "sabado": 5, "domingo": 6
    }
    
    for day_name, target_dow in dow_map.items():
        # Match "el lunes", "martes", "viernes"
        if day_name in user_text or f"el {day_name}" in user_text:
            # Calculate days ahead
            current_dow = now.weekday()
            # If "próximo" or "proximo" in text, add 7 days
            days_ahead = target_dow - current_dow
            if days_ahead <= 0 or "próximo" in user_text or "proximo" in user_text:
                days_ahead += 7
            
            target_date = now + timedelta(days=days_ahead)
            return target_date.replace(hour=10, minute=0, second=0)
    
    # Try "este lunes" etc
    for day_name, target_dow in dow_map.items():
        if f"este {day_name}" in user_text:
            current_dow = now.weekday()
            days_ahead = target_dow - current_dow
            if days_ahead <= 0:
                days_ahead += 7
            
            target_date = now + timedelta(days=days_ahead)
            return target_date.replace(hour=10, minute=0, second=0)
    
    logger.warning(f"[DateParser] Could NOT parse date: {user_text}")
    return None


def _parse_time(user_text: str) -> Optional[Tuple[int, int]]:
    """Parse time part of user input. Returns (hour, minute) or None if ambiguous."""
    
    # === Try explicit 24-hour format ===
    # "15:00", "16:30", "09:00"
    match = re.search(r'(\d{1,2}):(\d{2})', user_text)
    if match:
        hour = int(match.group(1))
        minute = int(match.group(2))
        if 0 <= hour <= 23 and 0 <= minute <= 59:
            return hour, minute
    
    # Just hour: "15hs", "a las 15"
    match = re.search(r'^a\s*las\s*(\d{1,2})$', user_text) or re.search(r'(\d{1,2})\s*hs?$', user_text)
    if match:
        hour = int(match.group(1))
        if 0 <= hour <= 23:
            return hour, 0
    
    # === Handle "am/pm" ===
    match = re.search(r'(\d{1,2})\s*(am|pm)', user_text)
    if match:
        hour = int(match.group(1))
        ampm = match.group(2).lower()
        if ampm == "pm" and hour < 12:
            hour += 12
        elif ampm == "am" and hour == 12:
            hour = 0
        if 0 <= hour <= 23:
            return hour, 0
    
    # === Spanish time expressions ===

    # PRIMERO: "a las X de la mañana/tarde/noche" — específico con hora explícita
    # Debe ir ANTES que los fallbacks genéricos para que "a las 8 de la mañana"
    # retorne 8:00 y no el fallback hardcodeado 10:00.
    match = re.search(r'a\s*las\s*(\d{1,2})\s*de\s*la\s*(mañana|tarde|noche)', user_text)
    if match:
        hour = int(match.group(1))
        period = match.group(2).lower()
        if period in ("tarde", "noche") and hour < 12:
            hour += 12
        if 0 <= hour <= 23:
            return hour, 0

    # "X de la mañana/tarde/noche" (sin "a las") — ej: "11 de la mañana", "3 de la tarde"
    match = re.search(r'(\d{1,2})\s+de\s+la\s+(mañana|tarde|noche)', user_text)
    if match:
        hour = int(match.group(1))
        period = match.group(2).lower()
        if period in ("tarde", "noche") and hour < 12:
            hour += 12
        if 0 <= hour <= 23:
            return hour, 0

    # "al mediodía" / "mediodía"
    if "mediod" in user_text or "mediodía" in user_text:
        return 12, 0  # 12:00

    # "esta tarde" - assume soonest available slot
    if "esta tarde" in user_text:
        return 15, 0

    # Fallbacks genéricos: solo aplican cuando NO hay un dígito de hora en el texto
    # "de la mañana" / "por la mañana" (sin hora específica)
    if ("mañana" in user_text and "de la" in user_text) or "por la mañana" in user_text:
        if not re.search(r'\d', user_text):
            return 10, 0  # 10:00

    # "de la tarde" / "por la tarde" (sin hora específica)
    if "tarde" in user_text and ("de la" in user_text or "por la" in user_text or user_text.strip() == "tarde"):
        if not re.search(r'\d', user_text):
            return 15, 0  # 15:00 (3pm)
    
    # === AMBIGUOUS - return None to force clarification ===
    # If text has date but no clear time
    if any(word in user_text for word in ["el ", "de abril", "de mayo", "hoy", "mañana"]):
        # Date present but no time = ambiguous
        logger.info(f"[DateParser] Time is ambiguous for: {user_text}")
        return None
    
    # Default to 10:00 only if very simple input and no date context
    if user_text in ("hoy", "mañana", "pasado"):
        return 10, 0
    
    # Fallback: if only a date-like word, ask for time
    return None


async def parse_datetime_llm(
    date_str: str,
    time_str: Optional[str],
    reference_dt: datetime,
) -> Tuple[Optional[datetime], Optional[str]]:
    """
    Resuelve expresiones de fecha/hora en lenguaje natural usando el LLM configurado.

    Returns:
        (datetime_aware, None)  → éxito
        (None, error_msg)       → fallo definitivo (responder al usuario con error_msg)
        (None, None)            → fallo técnico del LLM → el caller debe hacer fallback a regex
    """
    from app.agents.llm_router import llm_router

    combined = f"{date_str} {time_str or ''}".strip()
    ref_str = reference_dt.strftime("%Y-%m-%d %H:%M")

    system_prompt = (
        "Sos un parser de fechas para un sistema de citas inmobiliarias en Argentina.\n"
        "Zona horaria: America/Argentina/Buenos_Aires (UTC-3).\n"
        "Tu única tarea: convertir la expresión de fecha/hora del usuario a formato ISO.\n\n"
        "Reglas:\n"
        "- Respondé SOLO con 'YYYY-MM-DD HH:MM' (ejemplo: 2026-05-14 09:00).\n"
        "- 'de la mañana' = AM. 'de la tarde' o 'de la noche' = PM (sumá 12 si hora < 12).\n"
        "- 'mediodía' = 12:00. 'a la tardecita' ≈ 17:00.\n"
        "- Si solo dicen una hora sin período (ej: 'a las 3'), elegí la próxima ocurrencia futura.\n"
        "- Corregí typos comunes en días: 'vienes'=viernes, 'juves'=jueves, 'lune'=lunes, 'marte'=martes.\n"
        "- Si la hora no está especificada ni se puede inferir: respondé exactamente 'AMBIGUOUS: falta hora'.\n"
        "- Si la fecha no se puede determinar: respondé exactamente 'AMBIGUOUS: falta fecha'.\n"
        "- Nunca des explicaciones ni texto adicional."
    )

    user_message = (
        f"Fecha y hora actual: {ref_str}\n"
        f"Expresión del usuario: \"{combined}\""
    )

    try:
        result = await llm_router.chat(
            message=user_message,
            system_prompt=system_prompt,
            temperature=0,
            max_completion_tokens=20,
        )

        result = (result or "").strip()
        logger.info(f"[DateParser LLM] '{combined}' → '{result}'")

        if not result:
            logger.warning("[DateParser LLM] Respuesta vacía del LLM, haciendo fallback a regex")
            return None, None

        if result.upper().startswith("AMBIGUOUS"):
            reason = result.split(":", 1)[1].strip() if ":" in result else "expresión ambigua"
            return None, f"No pude determinar {reason}. ¿Podés ser más específico?"

        # Intentar parsear ISO
        try:
            naive_dt = datetime.strptime(result, "%Y-%m-%d %H:%M")
            aware_dt = ARG_TZ.localize(naive_dt)
            logger.info(f"[DateParser LLM] Éxito: {aware_dt.isoformat()}")
            return aware_dt, None
        except ValueError:
            logger.warning(f"[DateParser LLM] Formato inesperado: '{result}', fallback a regex")
            return None, None

    except Exception as e:
        logger.warning(f"[DateParser LLM] Error en llamada LLM: {e}, fallback a regex")
        return None, None


def format_datetime_argentina(dt: datetime) -> str:
    """Format datetime for display in Argentine format."""
    if dt.tzinfo is None:
        dt = ARG_TZ.localize(dt)
    
    dt_arg = dt.astimezone(ARG_TZ)
    return dt_arg.strftime("%d/%m/%Y a las %H:%M")


def validate_future(dt: datetime, min_minutes: int = 30) -> Tuple[bool, str]:
    """
    Validate that datetime is in the future.
    
    Args:
        dt: datetime to validate
        min_minutes: minimum minutes from now (default 30)
        
    Returns:
        (is_valid, error_message)
    """
    now = get_argentina_now()
    min_time = now + timedelta(minutes=min_minutes)
    
    if dt < min_time:
        return False, "La fecha/hora seleccionada ya pasó o está muy soon. Elige una hora con al menos 30 minutos de anticipación."
    
    return True, ""


# === Quick test ===
if __name__ == "__main__":
    test_cases = [
        # Explicit dates
        "mañana a las 15hs",
        "el viernes a las 10 de la mañana",
        "29/04/2026 18:00",
        "el 28 de abril a las 16:30",
        # Relative + tricky
        "el lunes que viene a las 4pm",
        "este viernes por la tarde",
        "la próxima semana al mediodía",
        "el próximo lunes",
        "este fin de semana",
        "pasado mañana",
        "hoy",
        # Ambiguous (should ask)
        "pronto",
        "en unos días",
        "la semana entrante",
    ]
    
    print("=" * 60)
    print("Testing Spanish Date/Time Parser (Advanced)")
    print("=" * 60)
    
    for text in test_cases:
        dt, error = parse_spanish_datetime(text)
        if error:
            print(f"  '{text}' -> ASK: {error}")
        else:
            print(f"  '{text}' -> {format_datetime_argentina(dt)}")

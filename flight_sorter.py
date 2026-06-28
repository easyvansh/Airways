import os
import re
import time
import threading

LAST_USED_PREFERENCES = {'value_meter': 5, 'excluded_airlines': [], 'max_stops': 3}

def main():
    current_directory = os.getcwd()
    for dirpath, dirnames, filenames in os.walk(current_directory):
        if 'all_trip_combinations' in dirnames:
            dirnames.remove('all_trip_combinations')
        if 'all_flight_permutations.txt' in filenames:
            file_path = os.path.join(dirpath, 'all_flight_permutations.txt')
            print(f"Processing file: {file_path}")
            try:
                process_file(file_path)
                print(f"Finished processing file: {file_path}\n")
            except Exception as e:
                print(f"An error occurred while processing {file_path}: {e}\n")

def process_file(file_path):
    global LAST_USED_PREFERENCES
    with open(file_path, 'r', encoding='utf-8') as f:
        content = f.read()

    trips = parse_content(content)

    if not trips:
        print("No trips found in the file.")
        return

    airlines_set = set()
    max_stops_in_data = 0
    for trip in trips:
        airlines_set.update([airline for airline in trip['airlines'] if airline])
        if trip['stops'] is not None and trip['stops'] > max_stops_in_data:
            max_stops_in_data = trip['stops']

    airlines_list = sorted(airlines_set)
    if not airlines_list:
        print("No airlines found in the trips.")
        return

    value_meter, excluded_airlines, max_user_stops = get_user_preferences(airlines_list, max_stops_in_data)

    filtered_trips = filter_and_sort_trips(trips, value_meter, excluded_airlines, max_user_stops)

    if not filtered_trips:
        print("No trips match your filters.")
        return

    output_file_path = os.path.join(os.path.dirname(file_path), 'sorted_flight_options.txt')
    generate_output(filtered_trips, output_file_path)
    print(f"Results saved to {output_file_path}")

    print_top_results(filtered_trips)

    update_last_used_preferences(value_meter, excluded_airlines, max_user_stops)

def parse_content(content):
    trips = []

    lines = content.splitlines()

    in_regular_trips = False
    in_split_trips = False

    regular_trip_pattern = re.compile(r'^(\d+):\s*(.*)')
    split_trip_pattern = re.compile(r'^(\d+[a-z]{2}):\s*(.*)')

    for line in lines:
        line = line.strip()
        if line == '':
            continue

        if line.startswith('Regular Trips Results:'):
            in_regular_trips = True
            in_split_trips = False
            continue
        elif line.startswith('Split Round-Trip Results:'):
            in_regular_trips = False
            in_split_trips = True
            continue
        elif line.startswith('='):
            continue
        elif in_regular_trips:
            match = regular_trip_pattern.match(line)
            if match:
                trip_number = match.group(1)
                trip_description = match.group(2)
                trip = parse_trip(trip_description, code=trip_number, trip_type='regular')
                trips.append(trip)
        elif in_split_trips:
            match = split_trip_pattern.match(line)
            if match:
                trip_code = match.group(1)
                trip_description = match.group(2)
                trip = parse_trip(trip_description, code=trip_code, trip_type='split')
                trips.append(trip)
    return trips

def parse_trip(description, code, trip_type):
    trip = {}
    trip['code'] = code
    trip['trip_type'] = trip_type
    trip['full_description'] = description

    price_pattern = re.compile(r'^From\s+([\d,\.]+)\s+([A-Za-z\s]+)\.')
    price_match = price_pattern.match(description)
    if price_match:
        price_str = price_match.group(1).replace(',', '')
        try:
            price = float(price_str)
        except ValueError:
            price = None
        currency = price_match.group(2).strip()
    else:
        price = None
        currency = None

    trip['price'] = price
    trip['currency'] = currency

    stops_airlines_pattern = re.compile(r'(\d+)\s+stops?\s+flight\s+with\s+(.+?)\.(.*)')
    stops_airlines_match = stops_airlines_pattern.search(description)
    if stops_airlines_match:
        stops = int(stops_airlines_match.group(1))
        airlines_str = stops_airlines_match.group(2)
        remaining_description = stops_airlines_match.group(3)
        airlines = [air.strip() for air in re.split(r',|and', airlines_str)]
        airlines = [air for air in airlines if air]
    else:
        nonstop_pattern = re.compile(r'Nonstop flight with (.+?)\.(.*)')
        nonstop_match = nonstop_pattern.search(description)
        if nonstop_match:
            stops = 0
            airlines_str = nonstop_match.group(1)
            airlines = [air.strip() for air in re.split(r',|and', airlines_str)]
            airlines = [air for air in airlines if air]
            remaining_description = nonstop_match.group(2)
        else:
            stops = None
            airlines = []
            remaining_description = description

    trip['stops'] = stops
    trip['airlines'] = airlines

    duration_pattern = re.compile(r'Total duration ([\d]+) hr(?: ([\d]+) min)?\.')
    duration_match = duration_pattern.search(description)
    if duration_match:
        hours = int(duration_match.group(1))
        minutes = int(duration_match.group(2)) if duration_match.group(2) else 0
        total_duration = hours * 60 + minutes
    else:
        total_duration = None

    trip['duration'] = total_duration

    trip['is_round_trip'] = 'round trip total' in description.lower()

    return trip

def get_user_preferences(airlines_list, max_stops_in_data):
    global LAST_USED_PREFERENCES

    default_preferences = {'value_meter': 5, 'excluded_airlines': [], 'max_stops': max_stops_in_data}

    user_preferences = LAST_USED_PREFERENCES.copy()

    if user_preferences['max_stops'] is None:
        user_preferences['max_stops'] = max_stops_in_data

    if user_preferences['max_stops'] > max_stops_in_data:
        print(f"Last used max stops ({user_preferences['max_stops']}) exceeds the maximum in current data ({max_stops_in_data}). Using {max_stops_in_data} instead.")
        user_preferences['max_stops'] = max_stops_in_data

    if user_preferences['excluded_airlines']:
        excluded_airlines = [air for air in user_preferences['excluded_airlines'] if air in airlines_list]
        if len(excluded_airlines) != len(user_preferences['excluded_airlines']):
            print("Some airlines from last used preferences are not found in current data and will be ignored.")
            user_preferences['excluded_airlines'] = excluded_airlines

    print(f"Do you want to use default sorting? (Value meter: {user_preferences.get('value_meter', 5)}, Excluded Airlines: {', '.join(user_preferences.get('excluded_airlines', [])) or 'None'}, Max Stops: {user_preferences.get('max_stops', max_stops_in_data)}) [Y/n] (Timeout in 60 seconds, default: Y)")

    def user_input(prompt, timeout, default=None):
        user_response = [None]
        def get_input():
            try:
                user_response[0] = input(prompt)
            except EOFError:
                user_response[0] = default
        thread = threading.Thread(target=get_input)
        thread.daemon = True
        thread.start()
        thread.join(timeout)
        if thread.is_alive():
            print(f"\nTimeout reached. Using default option: {default}")
            return default
        else:
            return user_response[0]

    response = user_input("> ", 60, default='y')
    if response is None or response.strip().lower() in ['y', 'yes', '']:
        if user_preferences:
            print("Using last used preferences.")
        else:
            print("Using default preferences.")
            user_preferences = default_preferences
    else:
        print("\nPlease enter a value between 1 and 10 to set your preference (1: Lowest Price, 10: Shortest Duration).")
        print("Press Enter to select default (5). (Timeout in 60 seconds)")
        value_meter_input = user_input("Value (1-10): ", 60, default='5')
        if value_meter_input.strip() == '':
            value_meter = 5
        else:
            try:
                value_meter = int(value_meter_input)
                if value_meter < 1 or value_meter > 10:
                    print("Invalid input. Defaulting to 5.")
                    value_meter = 5
            except ValueError:
                print("Invalid input. Defaulting to 5.")
                value_meter = 5

        print("\nAirlines found:")
        for idx, airline in enumerate(airlines_list):
            print(f"{idx+1}: {airline}")
        print(f"\nEnter the numbers of the airlines you want to exclude, separated by commas. (e.g., 1,3)")
        print(f"Or press Enter to skip (Timeout in 60 seconds, default: None)")
        exclude_input = user_input("> ", 60, default='')
        if exclude_input.strip() == '':
            excluded_airlines = []
        else:
            exclude_numbers = [int(x.strip()) for x in exclude_input.split(',') if x.strip().isdigit()]
            excluded_airlines = [airlines_list[i-1] for i in exclude_numbers if 0 < i <= len(airlines_list)]

        print(f"\nEnter the maximum number of stops (Max found: {max_stops_in_data}).")
        print(f"Press Enter to select default ({max_stops_in_data}). (Timeout in 60 seconds)")
        max_stops_input = user_input("> ", 60, default=str(max_stops_in_data))
        if max_stops_input.strip() == '':
            max_user_stops = max_stops_in_data
        else:
            try:
                max_user_stops = int(max_stops_input)
                if max_user_stops < 0:
                    print("Invalid input. Using default max stops.")
                    max_user_stops = max_stops_in_data
                elif max_user_stops > max_stops_in_data:
                    print(f"Entered max stops exceeds maximum in data. Using {max_stops_in_data} instead.")
                    max_user_stops = max_stops_in_data
            except ValueError:
                print("Invalid input. Using default max stops.")
                max_user_stops = max_stops_in_data

        user_preferences = {'value_meter': value_meter, 'excluded_airlines': excluded_airlines, 'max_stops': max_user_stops}

    return user_preferences['value_meter'], user_preferences['excluded_airlines'], user_preferences['max_stops']

def filter_and_sort_trips(trips, value_meter, excluded_airlines, max_user_stops):
    filtered_trips = []
    for trip in trips:
        if trip['stops'] is not None and trip['stops'] > max_user_stops:
            continue

        exclude = False
        for airline in trip['airlines']:
            individual_airlines = [air.strip() for air in airline.split(',')]
            for ind_air in individual_airlines:
                if ind_air in excluded_airlines:
                    exclude = True
                    break
            if exclude:
                break
        if exclude:
            continue

        filtered_trips.append(trip)

    if not filtered_trips:
        return []

    weight_price = (10 - value_meter) / 9
    weight_duration = (value_meter - 1) / 9

    prices = [trip['price'] for trip in filtered_trips if trip['price'] is not None]
    durations = [trip['duration'] for trip in filtered_trips if trip['duration'] is not None]

    if prices:
        avg_price = sum(prices) / len(prices)
    else:
        avg_price = 1
    if durations:
        avg_duration = sum(durations) / len(durations)
    else:
        avg_duration = 1

    for trip in filtered_trips:
        normalized_price = (trip['price'] / avg_price) if trip['price'] is not None else 1
        normalized_duration = (trip['duration'] / avg_duration) if trip['duration'] is not None else 1
        trip['value_score'] = weight_price * normalized_price + weight_duration * normalized_duration

    sorted_trips = sorted(filtered_trips, key=lambda x: x['value_score'])

    unique_trips = remove_duplicates(sorted_trips)

    return unique_trips

def remove_duplicates(trips):
    """
    Remove duplicate trips based on their full descriptions.
    Only the first occurrence of each unique description is kept.
    """
    seen_descriptions = set()
    unique_trips = []
    for trip in trips:
        identifier = trip['full_description']
        if identifier not in seen_descriptions:
            seen_descriptions.add(identifier)
            unique_trips.append(trip)
    return unique_trips

def generate_output(trips, output_file_path):
    is_round_trip = any(trip['is_round_trip'] for trip in trips)

    regular_trips = [trip for trip in trips if trip['trip_type'] == 'regular']
    split_trips = [trip for trip in trips if trip['trip_type'] == 'split']

    # Ensure duplicates are removed based on full description
    regular_trips = remove_duplicates(regular_trips)
    split_trips = remove_duplicates(split_trips)

    a_list_trips = []
    b_list_trips = []

    for trip in split_trips:
        if len(trip['code']) >= 3 and trip['code'][-2] == 'a':
            a_list_trips.append(trip)
        elif len(trip['code']) >= 3 and trip['code'][-2] == 'b':
            b_list_trips.append(trip)

    with open(output_file_path, 'w', encoding='utf-8') as f:
        if regular_trips or not (a_list_trips or b_list_trips):
            if is_round_trip:
                heading = "Round Trip Results:"
            else:
                heading = "One-way Trip Results:"
            f.write(f"{heading}\n")
            f.write('='*50 + '\n')
            if is_round_trip:
                f.write("Note: Only the departing flights are shown, but the full round trip price is displayed.\n\n")
            for idx, trip in enumerate(regular_trips, start=1):
                trip_str = format_trip(trip, idx)
                f.write(trip_str + '\n\n')

        if a_list_trips or b_list_trips:
            f.write('\nSplit Trip Results:\n')
            f.write('='*50 + '\n')
            if a_list_trips:
                f.write('Departing Flights:\n')
                f.write('-'*50 + '\n')
                for idx, trip in enumerate(a_list_trips, start=1):
                    trip_str = format_trip(trip, idx)
                    f.write(trip_str + '\n\n')
                f.write('-'*50 + '\n')
            if b_list_trips:
                f.write('Return Flights:\n')
                f.write('-'*50 + '\n')
                for idx, trip in enumerate(b_list_trips, start=1):
                    trip_str = format_trip(trip, idx)
                    f.write(trip_str + '\n\n')

def format_trip(trip, idx=None):
    if idx is not None:
        code_str = f"{idx}) {trip['code']}: "
    else:
        code_str = f"{trip['code']}: "
    trip_str = code_str + trip['full_description']
    return trip_str

def print_top_results(trips):
    regular_trips = [trip for trip in trips if trip['trip_type'] == 'regular']
    split_trips = [trip for trip in trips if trip['trip_type'] == 'split']

    # Ensure duplicates are removed based on full description
    regular_trips = remove_duplicates(regular_trips)
    split_trips = remove_duplicates(split_trips)

    a_list_trips = []
    b_list_trips = []

    for trip in split_trips:
        if len(trip['code']) >= 3 and trip['code'][-2] == 'a':
            a_list_trips.append(trip)
        elif len(trip['code']) >= 3 and trip['code'][-2] == 'b':
            b_list_trips.append(trip)

    if regular_trips:
        print("\nTop 5 Round Trips:")
        for idx, trip in enumerate(regular_trips[:5], start=1):
            print(f"{idx}) {trip['code']}: {trip['full_description']}")
    if a_list_trips:
        print("\nTop 5 Departing Flights:")
        for idx, trip in enumerate(a_list_trips[:5], start=1):
            print(f"{idx}) {trip['code']}: {trip['full_description']}")
    if b_list_trips:
        print("\nTop 5 Return Flights:")
        for idx, trip in enumerate(b_list_trips[:5], start=1):
            print(f"{idx}) {trip['code']}: {trip['full_description']}")
    if not (regular_trips or a_list_trips or b_list_trips):
        print("\nNo trips to display.")

def update_last_used_preferences(value_meter, excluded_airlines, max_user_stops):
    global LAST_USED_PREFERENCES
    LAST_USED_PREFERENCES = {'value_meter': value_meter, 'excluded_airlines': excluded_airlines, 'max_stops': max_user_stops}
    try:
        script_file = os.path.realpath(__file__)
        with open(script_file, 'r', encoding='utf-8') as f:
            lines = f.readlines()
        with open(script_file, 'w', encoding='utf-8') as f:
            for line in lines:
                if line.startswith('LAST_USED_PREFERENCES'):
                    f.write(f"LAST_USED_PREFERENCES = {LAST_USED_PREFERENCES}\n")
                else:
                    f.write(line)
    except Exception as e:
        print(f"Error updating last used preferences in script file: {e}")

if __name__ == '__main__':
    main()

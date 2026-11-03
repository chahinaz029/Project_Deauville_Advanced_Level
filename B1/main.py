import json
from collections import Counter

with open("data/festival.json", encoding="utf-8") as file:
    festival = json.load(file)
# 1. Afficher les lieux et calculer la capacité totale

print(festival["name"])
print(f"From {festival['first_day']} to {festival['last_day']}")
print(
    f"{len(festival['venues'])} venues, "
    f"{len(festival['artists'])} artists, "
    f"{len(festival['performances'])} performances"
)

# 1. Venues and total capacity
print("\nVenues:")

total_seats = 0

for venue in festival["venues"]:
    print(f"- {venue['name']}: {venue['capacity']} seats ({venue['address']})")
    total_seats += venue["capacity"]

print(f"Total: {total_seats} seats")


# 2. Count performances by kind

kind_counts = Counter(performance["kind"] for performance in festival["performances"])

for kind in ("lineup", "solo", "workshop"):
    print(f"\n{kind}: {kind_counts[kind]}")


# 3. Performances at Le Kiosque
print("\nAt Le Kiosque:")

kiosque_shows = []

for performance in festival["performances"]:
    if performance["venue"] == "le-kiosque":
        kiosque_shows.append(performance)

for performance in sorted(kiosque_shows, key=lambda p: p["start"]):
    print(f"- {performance['start']} {performance['title']}")


# 4. Longest performance
longest = max(festival["performances"], key=lambda p: p["duration_minutes"])

print(f"\nLongest: {longest['title']} ({longest['duration_minutes']} min)")


# 5. Workshops and registrations
for performance in festival["performances"]:
    if performance["kind"] == "workshop":
        day = performance["start"][:10]
        registered = len(performance["participants"])
        places = performance["max_participants"]

        print(f"{performance['title']} on {day}: {registered}/{places} registered")


# 6. Artists appearing most often
artist_counts = Counter()

for performance in festival["performances"]:
    for role in ("artist", "host", "teacher"):
        if role in performance:
            artist_counts[performance[role]] += 1

    artist_counts.update(performance.get("acts", []))

if artist_counts:
    most_appearances = max(artist_counts.values())

    most_frequent = sorted(
        artist_id
        for artist_id, count in artist_counts.items()
        if count == most_appearances
    )

    print(f"\nOn stage {most_appearances} times: {', '.join(most_frequent)}")


# 1. Build the list of festival days from the performances
days = sorted({performance["start"][:10] for performance in festival["performances"]})

# 2. Ask for a valid day
while True:
    day = input("Day (YYYY-MM-DD): ")

    if day in days:
        break

    print(f"No performance on '{day}'. Days: {', '.join(days)}")


# 3. Build a dictionary to match venue IDs to venue names
venues = {}

for venue in festival["venues"]:
    venue_id = (
        venue["name"].replace("é", "e").replace("â", "a").lower().replace(" ", "-")
    )
    venues[venue_id] = venue["name"]


# Print the performances for the selected day
print(f"Programme for {day}:")

performances = [
    performance
    for performance in festival["performances"]
    if performance["start"][:10] == day
]

for performance in sorted(performances, key=lambda p: p["start"]):
    time = performance["start"][11:16]
    venue_name = venues[performance["venue"]]
    title = performance["title"]
    kind = performance["kind"]

    print(f"{time} | {venue_name} | {title} ({kind})")

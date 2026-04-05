from django.shortcuts import render, get_object_or_404
from .models import Race, Club, Station


def home(request):
    return render(request, "race_results/home.html")


from django.shortcuts import render, get_object_or_404
from .models import Race, Club, Station

def race_list(request):
    season_year = request.GET.get("season_year", "").strip()
    category = request.GET.get("category", "").strip()
    club_id = request.GET.get("club", "").strip()
    station_id = request.GET.get("station", "").strip()

    # dropdowns
    clubs = Club.objects.all().order_by("name")
    stations = Station.objects.all().order_by("name")
    years = [y for (y, _) in Race.YEAR_CHOICES]
    categories = Race.CATEGORY_CHOICES

    # ✅ SI NO HAN FILTRADO NADA -> TABLA VACÍA
    if not (season_year or category or club_id or station_id):
        races = Race.objects.none()
    else:
        races = Race.objects.select_related("club", "station").all().order_by(
            "-season_year", "category", "station__name", "race_number"
        )

        if season_year:
            races = races.filter(season_year=season_year)
        if category:
            races = races.filter(category=category)
        if club_id:
            races = races.filter(club_id=club_id)
        if station_id:
            races = races.filter(station_id=station_id)

    context = {
        "races": races,
        "clubs": clubs,
        "stations": stations,
        "years": years,
        "categories": categories,
        "selected": {
            "season_year": season_year,
            "category": category,
            "club": club_id,
            "station": station_id,
        }
    }

    return render(request, "race_results/race_list.html", context)


def race_detail(request, pk):
    race = get_object_or_404(
        Race.objects.select_related("club", "station"),
        pk=pk
    )

    # 👇 aquí traemos los resultados (RaceEntry) de esa carrera
    entries = race.entries.select_related("pigeon", "pigeon__member").order_by("pos")

    return render(request, "race_results/race_detail.html", {
        "race": race,
        "entries": entries,
    })



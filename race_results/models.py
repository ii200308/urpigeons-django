import math
from datetime import datetime as dt_datetime
from decimal import Decimal, ROUND_HALF_UP
from django.core.exceptions import ValidationError
from django.core.validators import MinValueValidator
from django.db import models, transaction
from django.utils import timezone
import datetime


# ---------- Helpers ----------
def haversine_miles(lat1, lon1, lat2, lon2) -> float:
    """Distancia en millas entre dos puntos (lat/lon) usando Haversine."""
    R = 3958.7613  # radio tierra en millas

    lat1 = math.radians(float(lat1))
    lon1 = math.radians(float(lon1))
    lat2 = math.radians(float(lat2))
    lon2 = math.radians(float(lon2))

    dlat = lat2 - lat1
    dlon = lon2 - lon1

    a = (
        math.sin(dlat / 2) ** 2
        + math.cos(lat1) * math.cos(lat2) * math.sin(dlon / 2) ** 2
    )
    c = 2 * math.asin(math.sqrt(a))
    return R * c


def q2(x) -> Decimal:
    """Decimal a 2 decimales."""
    return Decimal(x).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)


def q3(x) -> Decimal:
    """Decimal a 3 decimales."""
    return Decimal(x).quantize(Decimal("0.001"), rounding=ROUND_HALF_UP)


# ---------- Models ----------
class Club(models.Model):
    name = models.CharField(max_length=120, unique=True)
    acronym = models.CharField(max_length=20, blank=True, default="")  # BRPC, etc

    def __str__(self):
        return f"{self.acronym} - {self.name}" if self.acronym else self.name


class Station(models.Model):
    name = models.CharField(max_length=100, unique=True)

    official_miles = models.PositiveIntegerField(
        validators=[MinValueValidator(1)], default=100
    )

    def __str__(self):
        return f"{self.name} ({self.official_miles} mi)"


class Member(models.Model):
    club = models.ForeignKey(Club, on_delete=models.PROTECT, related_name="members")
    name = models.CharField(max_length=120)
    loft_name = models.CharField(max_length=120, blank=True, default="")
    active = models.BooleanField(default=True)

    # IMPORTANTE: por ahora permitimos NULL para que migre sin pedir default.
    latitude = models.DecimalField(
        max_digits=9, decimal_places=6, null=True, blank=True
    )
    longitude = models.DecimalField(
        max_digits=9, decimal_places=6, null=True, blank=True
    )

    def __str__(self):
        return f"{self.name} ({self.loft_name})" if self.loft_name else self.name

    def clean(self):
        # obligatorias SOLO al crear (admin también lo refuerza)
        if not self.pk and (self.latitude is None or self.longitude is None):
            raise ValidationError(
                "Latitude and longitude are required to register a member."
            )


class Pigeon(models.Model):
    ORG_CHOICES = [
        ("AU", "AU"),
        ("IF", "IF"),
        ("CU", "CU"),
        ("NBRC", "NBRC"),
        ("OTHER", "OTHER"),
    ]
    YEAR_CHOICES = [(y, str(y)) for y in range(2024, 2036)]

    member = models.ForeignKey(Member, on_delete=models.PROTECT, related_name="pigeons")

    band_number = models.CharField(max_length=10, blank=True, null=True)  # 12345
    organization = models.CharField(max_length=10, choices=ORG_CHOICES, default="AU")
    band_year = models.PositiveIntegerField(choices=YEAR_CHOICES, default=2026)
    letters = models.CharField(max_length=30, blank=True, null=True)  # BRPC

    color = models.CharField(max_length=30, blank=True, default="")
    sex = models.CharField(
        max_length=1,
        choices=[("C", "Cock"), ("H", "Hen"), ("U", "Unknown")],
        default="U",
    )

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=["band_number", "organization", "band_year", "letters"],
                name="unique_ring_id",
            )
        ]

    @property
    def band_id(self):
        year_2 = str(self.band_year)[-2:]  # 2026 -> "26"
        return f"{self.band_number}-{self.organization}-{year_2}-{self.letters}"

    def __str__(self):
        return self.band_id


class Race(models.Model):
    CATEGORY_CHOICES = [
        ("OB", "Old Birds"),
        ("YB", "Young Birds"),
    ]
    YEAR_CHOICES = [(y, str(y)) for y in range(2024, 2036)]

    season_year = models.PositiveIntegerField(choices=YEAR_CHOICES, default=2026)
    category = models.CharField(max_length=10, choices=CATEGORY_CHOICES, default="OB")

    club = models.ForeignKey(Club, on_delete=models.PROTECT, related_name="races")
    station = models.ForeignKey(Station, on_delete=models.PROTECT, related_name="races")

    race_number = models.PositiveIntegerField(default=1)

    release_date = models.DateField(null=True, blank=True)
    release_time = models.TimeField(null=True, blank=True)

    # Coordenadas reales del punto de suelta (pueden variar aunque sea el mismo Station)
    release_latitude = models.DecimalField(
        max_digits=9, decimal_places=6, null=True, blank=True
    )
    release_longitude = models.DecimalField(
        max_digits=9, decimal_places=6, null=True, blank=True
    )

    birds_sent = models.PositiveIntegerField(default=0)
    lofts_sent = models.PositiveIntegerField(default=0)

    # “millas oficiales” (solo referencia); lo real se calcula por asociado en RaceEntry
    miles = models.PositiveIntegerField(default=0, editable=False)

    created_at = models.DateTimeField(default=timezone.now, editable=False)

    class Meta:
        unique_together = ("season_year", "category", "club", "station", "race_number")

    def save(self, *args, **kwargs):
        if self.station:
            self.miles = self.station.official_miles

        # auto race_number por combinación
        if not self.pk:
            last = (
                Race.objects.filter(
                    season_year=self.season_year,
                    category=self.category,
                    club=self.club,
                    station=self.station,
                )
                .order_by("-race_number")
                .first()
            )
            self.race_number = (last.race_number + 1) if last else 1

        super().save(*args, **kwargs)

    @property
    def name(self):
        return f"{self.station.name} #{self.race_number}"

    def __str__(self):
        return self.name

    def update_counts(self):
        """
        Actualiza conteos derivados.
        - lofts_sent: lofts distintos con entries
        - birds_sent: NO lo sobrescribimos si ya fue introducido manualmente.
          Si está en 0, entonces sí lo calculamos desde entries.
        """
        if not self.birds_sent:
            self.birds_sent = self.entries.count()
        self.lofts_sent = self.entries.values("pigeon__member").distinct().count()
        self.save(update_fields=["birds_sent", "lofts_sent"])


    def get_release_datetime(self):
        if not self.release_date or not self.release_time:
            return None
        dt = dt_datetime.combine(self.release_date, self.release_time)
        if timezone.is_naive(dt):
            dt = timezone.make_aware(dt, timezone.get_current_timezone())
        return dt

    def miles_for_member(self, member: Member) -> float:
        if not (
            self.release_latitude
            and self.release_longitude
            and member.latitude
            and member.longitude
        ):
            return 0.0
        return haversine_miles(
            member.latitude,
            member.longitude,
            self.release_latitude,
            self.release_longitude,
        )

    def recalc_positions_and_points(self):
        """Recalculate positions, points, and 'to_win' (minutes behind winner) for all entries in this race."""
        entry_model = self.entries.model

        entries = list(
            self.entries.select_related("pigeon", "pigeon__member")
            .filter(arrival_time__isnull=False)
            .order_by("-ypm", "arrival_time", "id")
        )

        if not entries:
            return

        # ---- Positions (NO ties) ----
        for idx, e in enumerate(entries, start=1):
            e.pos = idx

        winner = entries[0]
        winner_arrival = winner.arrival_time

        # ---- TO WIN (minutes behind winner) ----
        for e in entries:
            if winner_arrival and e.arrival_time:
                delta_min = (e.arrival_time - winner_arrival).total_seconds() / 60.0
                if delta_min < 0:
                    delta_min = 0.0
                e.to_win = q2(Decimal(str(delta_min)))
            else:
                e.to_win = Decimal("0.00")

        # ---- POINTS ----
        N_total = int(self.birds_sent or self.entries.count())
        N_arrivals = len(entries)

        if N_total <= 0:
            for e in entries:
                e.df_points = Decimal("0.00")
            entry_model.objects.bulk_update(entries, ["pos", "df_points", "to_win"])
            return

        # 20% de enviadas, redondeado por exceso
        cutoff = math.ceil(N_total * 0.20)

        # no pueden puntuar más de las que llegaron
        cutoff = min(cutoff, N_arrivals)

        miles_official = Decimal(str(self.miles or 0))
        base_points = (miles_official * Decimal("1.6")) / Decimal("2")
        bonus = base_points + Decimal("1")

        # Si solo hay una posición puntuable
        if cutoff == 1:
            winning_points = q2(base_points + bonus)
            for idx, e in enumerate(entries, start=1):
                e.df_points = winning_points if idx == 1 else Decimal("0.00")

            entry_model.objects.bulk_update(entries, ["pos", "df_points", "to_win"])
            return

        # Descenso lineal hasta 0 + bonus en la última puntuable
        drop = base_points / Decimal(cutoff - 1)

        for idx, e in enumerate(entries, start=1):
            if idx > cutoff:
                e.df_points = Decimal("0.00")
                continue

            raw_points = base_points - (Decimal(idx - 1) * drop)
            if raw_points < 0:
                raw_points = Decimal("0")

            e.df_points = q2(raw_points + bonus)

        entry_model.objects.bulk_update(entries, ["pos", "df_points", "to_win"])

class RaceEntry(models.Model):

    to_win = models.DecimalField(
        max_digits=7,
        decimal_places=2,
        default=Decimal("0.00"),
        verbose_name="To Win (min)",
    )

    df_points = models.DecimalField(
        max_digits=7,
        decimal_places=2,
        default=Decimal("0.00"),
        verbose_name="Points",
    )

    race = models.ForeignKey(Race, on_delete=models.CASCADE, related_name="entries")
    pigeon = models.ForeignKey(
        Pigeon, on_delete=models.PROTECT, related_name="race_entries"
    )

    pos = models.PositiveIntegerField(validators=[MinValueValidator(1)], default=1)
    arrival_time = models.DateTimeField(null=True, blank=True)

    # distancia real (millas) calculada
    miles = models.DecimalField(
        max_digits=8, decimal_places=3, default=Decimal("0.000")
    )

    # velocidad (yards per minute) calculada
    ypm = models.DecimalField(max_digits=10, decimal_places=3, default=Decimal("0.000"))

    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["pos"]
        unique_together = ("race", "pigeon")

    def __str__(self):
        return f"{self.race} - {self.pigeon} (#{self.pos})"

    def clean(self):
        """
        Reglas de consistencia:
        - Arrival Time NO puede ser antes o igual que Release Date+Release Time
        """
        super().clean()

        # Si todavía no hay race o arrival_time, no validamos
        if not self.race_id or not self.arrival_time:
            return

        release_dt = self.race.get_release_datetime()
        if not release_dt:
            return  # todavía no hay suelta completa

        if self.arrival_time <= release_dt:
            raise ValidationError(
                {
                    "arrival_time": "Arrival Time no puede ser antes (o igual) que la hora de suelta."
                }
            )

    def compute(self):
        """Calcula miles reales y YPM (con 3 decimales) basado en coords y tiempos."""
        release_dt = self.race.get_release_datetime()
        if not release_dt or not self.arrival_time:
            self.miles = Decimal("0.000")
            self.ypm = Decimal("0.000")
            return

        member = self.pigeon.member
        miles_f = float(self.race.miles_for_member(member))
        self.miles = q3(Decimal(str(miles_f)))

        # ypm = yards / minutes
        yards = Decimal(str(miles_f)) * Decimal("1760")
        minutes = Decimal(str((self.arrival_time - release_dt).total_seconds() / 60.0))
        if minutes <= 0:
            self.ypm = Decimal("0.000")
            return
        ypm_value = yards / minutes
        self.ypm = q3(ypm_value)

    def save(self, *args, **kwargs):
        with transaction.atomic():
            self.full_clean()
            self.compute()
            super().save(*args, **kwargs)
            self.race.recalc_positions_and_points()
            self.race.update_counts()

    def delete(self, *args, **kwargs):
        race = self.race
        super().delete(*args, **kwargs)
        race.recalc_positions_and_points()
        race.update_counts()

from django.db import models


class Member(models.Model):
    club = models.ForeignKey("race_results.Club", on_delete=models.PROTECT, related_name="members")
    name = models.CharField(max_length=120)

    # opcional
    phone = models.CharField(max_length=30, blank=True, default="")
    loft_code = models.CharField(max_length=30, blank=True, default="")

    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        unique_together = ("club", "name")

    def __str__(self):
        return f"{self.name} ({self.club})"


class Pigeon(models.Model):
    owner = models.ForeignKey(Member, on_delete=models.PROTECT, related_name="pigeons")

    band = models.CharField(max_length=50, unique=True)  # anilla
    sex = models.CharField(max_length=1, choices=[("M", "Male"), ("F", "Female"), ("U", "Unknown")], default="U")

    hatch_year = models.PositiveIntegerField(null=True, blank=True)
    color = models.CharField(max_length=50, blank=True, default="")
    strain = models.CharField(max_length=80, blank=True, default="")

    notes = models.TextField(blank=True, default="")
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f"{self.band} - {self.owner.name}"

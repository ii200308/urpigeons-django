from django.db import transaction
from django.db.models.signals import post_save, post_delete
from django.dispatch import receiver

from .models import RaceEntry


def reorder_positions_for_race(race_id: int) -> None:
    """
    Reasigna pos = 1..N ordenando por:
      - ypm DESC (mayor primero)
      - arrival_time ASC (si empatan ypm, el que llegó antes gana)
      - id ASC (último desempate estable)
    """
    entries = (
        RaceEntry.objects
        .filter(race_id=race_id)
        .select_for_update()
        .order_by("-ypm", "arrival_time", "id")
    )

    updates = []
    for i, e in enumerate(entries, start=1):
        if e.pos != i:
            e.pos = i
            updates.append(e)

    if updates:
        RaceEntry.objects.bulk_update(updates, ["pos"])


@receiver(post_save, sender=RaceEntry)
def raceentry_post_save(sender, instance: RaceEntry, **kwargs):
    # Espera a que la transacción se confirme antes de reordenar.
    transaction.on_commit(lambda: _safe_reorder(instance.race_id))


@receiver(post_delete, sender=RaceEntry)
def raceentry_post_delete(sender, instance: RaceEntry, **kwargs):
    transaction.on_commit(lambda: _safe_reorder(instance.race_id))


def _safe_reorder(race_id: int) -> None:
    # Agrupamos el reorder dentro de una transacción para evitar condiciones de carrera
    with transaction.atomic():
        reorder_positions_for_race(race_id)

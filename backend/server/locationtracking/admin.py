from django.contrib import admin

from .models import (
    JourneyCandidate,
    JourneyStop,
    LocationDevice,
    LocationSample,
    LocationTrackingAuditEvent,
    PrivacyEvent,
    PrivacyZone,
    StayCandidate,
)


admin.site.register(LocationDevice)
admin.site.register(PrivacyZone)
admin.site.register(PrivacyEvent)
admin.site.register(LocationSample)
admin.site.register(StayCandidate)
admin.site.register(JourneyCandidate)
admin.site.register(JourneyStop)
admin.site.register(LocationTrackingAuditEvent)

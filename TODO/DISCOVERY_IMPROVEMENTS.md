# Topic Discovery Improvements Plan

**Created:** December 14, 2025  
**Branch:** feature/ovms-firmware-improvements  
**Status:** ✅ IMPLEMENTED

## Background

Analysis of topic discovery code identified three issues that could affect user experience in certain scenarios.

## Issues to Fix

### Issue 1: Echo Falsely Triggers "Active Success"

**Problem:**  
When publishing to `request/metric`, the MQTT broker may echo our own message back. This single echoed message counts as "1 new topic", causing the code to think active discovery worked when it actually didn't get any real metrics.

**Affected Scenarios:**
- Scenario 2: Fresh MQTT + Stable firmware (no Edge support)
- Scenario 5: Fresh MQTT + Module offline

**Current Code Location:**  
`custom_components/ovms/config_flow/topic_discovery.py` lines 385-400

**Current Behavior:**
```python
topics_after_active = len(discovered_topics)
new_topics = topics_after_active - topics_before_active

if new_topics > 0:  # Echo counts as 1!
    active_discovery_succeeded = True
```

**Fix:**  
Filter out topics containing `/client/` from the new topic count, as these are command/response topics, not metric topics.

**Implementation:**
```python
# Count only metric topics (exclude /client/ topics which include our echo)
def count_metric_topics(topics):
    return sum(1 for t in topics if "/metric/" in t)

topics_before_active = count_metric_topics(discovered_topics)
# ... wait ...
topics_after_active = count_metric_topics(discovered_topics)
new_topics = topics_after_active - topics_before_active
```

**Verification:**
- [x] Active discovery only "succeeds" when actual metric topics are received
- [x] Echo of request/metric topic is not counted
- [x] Logs correctly show "0 new metric topics" when only echo received
- [x] Falls back to legacy discovery when no real metrics received

---

### Issue 2: No Minimum Topic Validation

**Problem:**  
Discovery "succeeds" (returns `success: True`) even with 0 topics found. User can proceed through config flow with no data, leading to a broken integration setup.

**Affected Scenarios:**
- Scenario 5: Fresh MQTT + Module offline

**Current Code Location:**  
`custom_components/ovms/config_flow/topic_discovery.py` lines 480-495

**Current Behavior:**
```python
return {
    "success": True,  # Always true if MQTT connected!
    "discovered_topics": discovered_topics,
    "topic_count": topics_count,
    "debug_info": debug_info,
}
```

**Fix:**  
Add a minimum topic threshold constant and return appropriate status.

**Implementation:**
```python
# In const.py
MINIMUM_DISCOVERY_TOPICS = 5  # Minimum topics for valid discovery

# In topic_discovery.py
topics_count = len(discovered_topics)
metric_topics = [t for t in discovered_topics if "/metric/" in t]
metric_count = len(metric_topics)

if metric_count < MINIMUM_DISCOVERY_TOPICS:
    return {
        "success": True,  # MQTT worked, but...
        "discovered_topics": discovered_topics,
        "topic_count": topics_count,
        "metric_count": metric_count,
        "warning": "few_topics",  # New field for UI to show warning
        "debug_info": debug_info,
    }
```

**Config Flow Update:**  
`custom_components/ovms/config_flow/__init__.py` should check for `warning` field and display appropriate message to user.

**Verification:**
- [x] Discovery with 0 topics returns warning flag
- [x] Discovery with 1-4 topics returns warning flag
- [x] Discovery with 5+ metric topics returns no warning
- [x] Config flow shows warning message when few topics found
- [x] User can still proceed (module may come online later)

---

### Issue 3: No User Feedback on Discovery Quality

**Problem:**  
User sees "174 topics found" but doesn't know if that's good, bad, or if their module is even responding. No guidance on what to do if discovery seems incomplete.

**Affected Scenarios:**
- All scenarios benefit from better feedback

**Current Code Location:**  
`custom_components/ovms/config_flow/__init__.py` lines 348-365 (description_placeholders)

**Current Behavior:**
```python
description_placeholders={
    "topic_count": str(topics_count),
    "sample_topic1": sample_topics[0],
    # ...
}
```

**Fix:**  
Add discovery quality indicator and guidance message.

**Implementation:**
```python
# Determine discovery quality
if metric_count >= 50:
    discovery_quality = "excellent"
    quality_message = "Your OVMS module is responding well."
elif metric_count >= 20:
    discovery_quality = "good"
    quality_message = "Discovery looks good."
elif metric_count >= MINIMUM_DISCOVERY_TOPICS:
    discovery_quality = "partial"
    quality_message = "Partial data received. Some entities may be missing."
elif metric_count > 0:
    discovery_quality = "minimal"
    quality_message = "Very few topics found. Check that your OVMS module is online and publishing metrics."
else:
    discovery_quality = "none"
    quality_message = "No topics found. Ensure your OVMS module is connected and configured to publish via MQTT."

description_placeholders={
    "topic_count": str(topics_count),
    "metric_count": str(metric_count),
    "discovery_quality": discovery_quality,
    "quality_message": quality_message,
    # ...
}
```

**Translation Updates:**  
Add quality messages to `translations/en.json` and `translations/strings.json`.

**Verification:**
- [x] "excellent" shown for 50+ metric topics
- [x] "good" shown for 20-49 metric topics
- [x] "partial" shown for 5-19 metric topics
- [x] "minimal" shown for 1-4 metric topics
- [x] "none" shown for 0 metric topics
- [x] Guidance message helps user understand next steps

---

## Implementation Order

1. **Issue 1** (Echo filter) - Most critical, prevents false success
2. **Issue 2** (Minimum validation) - Adds warning system
3. **Issue 3** (Quality feedback) - Improves UX

## Files to Modify

| File | Changes |
|------|---------|
| `const.py` | Add `MINIMUM_DISCOVERY_TOPICS` constant |
| `config_flow/topic_discovery.py` | Fix echo counting, add warning field |
| `config_flow/__init__.py` | Handle warning, add quality indicator |
| `translations/en.json` | Add quality messages |
| `translations/strings.json` | Add quality messages |

## Testing Checklist

After implementation, verify:

- [ ] Scenario 1 (Fresh + Edge + Online): Still works, shows "excellent"
- [ ] Scenario 2 (Fresh + Stable + Online): Falls back to legacy correctly
- [ ] Scenario 3 (Retained + Online): Works, shows appropriate quality
- [ ] Scenario 4 (Retained + Offline): Works with stale data
- [ ] Scenario 5 (Fresh + Offline): Shows warning, user informed
- [ ] Scenario 6 (No Retain): Falls back correctly, shows quality

## Rollback Plan

If issues arise:
1. Revert changes to `topic_discovery.py`
2. Keep translations (harmless)
3. Remove constant from `const.py`

---

## Notes

- All changes are backward compatible
- Existing users won't see any difference if their setup works
- Only users with problematic setups benefit from better feedback
- No breaking changes to config flow structure

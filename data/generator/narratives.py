"""Clinical narratives, written to satisfy or miss specific policy criteria.

These are the free-text blocks that appear in the "clinical justification"
section of the pre-auth form, and they are the only input to the medical
necessity judgment. Each is written against the numbered criteria in the
matching medical policy document (see corpus.py), so a gold label can name
exactly which criterion the narrative does or does not support.

Three flavours per procedure:
  met          -- every criterion is affirmatively documented
  unmet        -- the record contradicts a criterion (supports a denial)
  no_evidence  -- the record is silent on a criterion (supports a pend)

The distinction between the last two is the point. A narrative that says
"conservative therapy was not attempted" is a different case from one that
simply never mentions conservative therapy, and a system that denies both is
denying care for a paperwork reason.
"""

from __future__ import annotations

# --------------------------------------------------------------------------
# 72148 -- MRI lumbar spine without contrast
# --------------------------------------------------------------------------

MRI_LUMBAR_MET = """\
{age}-year-old presenting with axial low back pain radiating into the left
lower extremity, onset approximately four months ago after a lifting injury
at work. Pain is rated 7/10 and worse with sitting and forward flexion.

Conservative management: completed 8 weeks of supervised physical therapy
(24 visits, 06/02/2026 through 07/28/2026) with documented adherence, plus a
scheduled course of meloxicam 15 mg daily and a two-week trial of
cyclobenzaprine. Symptoms have not improved; the patient reports no
meaningful change in functional capacity.

Neurologic examination: diminished left patellar reflex (1+ compared with 2+
on the right), decreased sensation in the L4 dermatome, and 4/5 strength on
left ankle dorsiflexion. Straight leg raise positive at 40 degrees on the
left.

Plain radiographs of the lumbar spine (2 views, 07/30/2026) demonstrate disc
space narrowing at L4-L5 without acute fracture or spondylolisthesis.

The patient has been referred for neurosurgical consultation and MRI is
required to determine whether a surgical decompression is indicated.
"""

MRI_LUMBAR_UNMET = """\
{age}-year-old with a two-week history of low back pain following a weekend
move. Pain is localised to the lower lumbar region and rated 4/10.

The patient has not attempted physical therapy and declined a trial of
NSAIDs, preferring to proceed directly to imaging. No course of conservative
management has been undertaken.

Neurologic examination is normal: reflexes 2+ and symmetric, sensation
intact throughout, 5/5 strength in all lower extremity muscle groups.
Straight leg raise negative bilaterally. No bowel or bladder dysfunction, no
saddle anaesthesia, no fever, no history of malignancy, no unexplained
weight loss.

No plain radiographs have been obtained.

The patient requests MRI for reassurance.
"""

MRI_LUMBAR_NO_EVIDENCE = """\
{age}-year-old with ongoing low back pain radiating into the right leg.
Symptoms have been present for several months and continue to limit daily
activity.

Examination shows reduced sensation in the right L5 distribution and a
positive straight leg raise on the right at approximately 45 degrees.

Plain films of the lumbar spine were obtained on 07/22/2026 and show mild
degenerative change at L4-L5 and L5-S1.

Requesting MRI lumbar spine to further evaluate.
"""

# --------------------------------------------------------------------------
# 27447 -- Total knee arthroplasty
# --------------------------------------------------------------------------

TKA_MET = """\
{age}-year-old with a five-year history of progressive right knee pain now
rated 8/10 at rest and 9/10 with ambulation. The patient is unable to walk
more than one block and has stopped using stairs.

Conservative management over the past 14 months: supervised physical therapy
(three separate courses, 36 visits total), naproxen 500 mg twice daily,
two intra-articular corticosteroid injections (11/2025 and 03/2026) each
giving less than six weeks of relief, activity modification, and a cane.

Weight-bearing radiographs of the right knee dated 07/14/2026 demonstrate
bone-on-bone medial compartment narrowing with subchondral sclerosis and
marginal osteophytes, consistent with Kellgren-Lawrence grade 4
osteoarthritis.

BMI is 31.2. The patient has completed a preoperative medical evaluation and
is cleared for surgery. Symptoms substantially limit activities of daily
living despite maximal non-operative management.
"""

TKA_NO_EVIDENCE = """\
{age}-year-old with longstanding right knee osteoarthritis and increasing pain
that limits walking distance. Reports the knee "gives way" on uneven ground.

Examination shows a moderate effusion, crepitus through range of motion, and
a 10-degree flexion contracture. Range of motion 10 to 105 degrees.

The patient wishes to proceed with total knee replacement.
"""

# --------------------------------------------------------------------------
# 15823 -- Blepharoplasty, upper eyelid
# --------------------------------------------------------------------------

BLEPH_FUNCTIONAL = """\
{age}-year-old with progressive bilateral upper eyelid drooping over three
years, now obscuring vision when reading and driving.

Visual field testing dated 07/09/2026 demonstrates a superior field deficit
of 28 degrees on the right, improving to 12 degrees with the lid manually
elevated -- a 16-degree improvement on taping.

External photographs document a margin-to-reflex distance of 1.5 mm on the
right. The patient reports compensatory brow elevation and frontal headache
by end of day.

This is a functional repair to restore the superior visual field, not a
cosmetic procedure.
"""

BLEPH_COSMETIC = """\
{age}-year-old requesting upper eyelid surgery for a tired appearance. The
patient is troubled by the look of the upper lids in photographs and would
like a more rested appearance before a family wedding.

Visual fields are full to confrontation. No ptosis. Margin-to-reflex
distance 4 mm bilaterally. No functional complaint and no compensatory brow
elevation.
"""

# --------------------------------------------------------------------------
# 64483 -- Lumbar transforaminal epidural steroid injection
# --------------------------------------------------------------------------

ESI_BORDERLINE = """\
{age}-year-old with right-sided radicular leg pain rated 6/10, present for
approximately seven weeks.

The patient completed four weeks of physical therapy with partial benefit
and reports the home exercise programme has been followed inconsistently due
to work schedule. A course of gabapentin was started three weeks ago and
titrated to 900 mg daily.

Examination shows a positive straight leg raise on the right. Reflexes are
symmetric and strength is 5/5 throughout; sensory examination is described
as "subjectively reduced" in the right calf without a clear dermatomal
pattern.

MRI dated 06/28/2026 shows a right paracentral disc protrusion at L5-S1
with contact on the traversing S1 nerve root. Whether this fully accounts
for the reported distribution is uncertain.
"""

# --------------------------------------------------------------------------
# Generic narratives for procedures that do not need authorization
# --------------------------------------------------------------------------

ROUTINE_OFFICE_VISIT = """\
Established patient presenting for routine follow-up of type 2 diabetes.
Last A1c 7.1%. Medication adherence good. No hypoglycaemic episodes
reported. Requesting authorization prior to the visit per office policy.
"""

ROUTINE_CHEST_XRAY = """\
Patient with a productive cough for eight days and low-grade fever.
Requesting chest radiograph, 2 views, to exclude pneumonia. Submitting
authorization request per practice protocol.
"""

ROUTINE_LAB_PANEL = """\
Routine metabolic panel for ongoing monitoring of type 2 diabetes and
antihypertensive therapy. Submitted for authorization as part of the
standing order set.
"""

ROUTINE_PT = """\
Continuing outpatient physical therapy for low back pain, therapeutic
exercise. Requesting authorization for a further block of visits.
"""

ROUTINE_COLONOSCOPY = """\
{age}-year-old presenting for average-risk colorectal cancer screening.
No family history of colorectal malignancy, no rectal bleeding, no change in
bowel habit. Submitting for authorization prior to scheduling.
"""


#: Narratives for the no-auth-required fast path, keyed by procedure code.
#: Each is a provider dutifully submitting a request for something that never
#: needed one -- which is exactly the clerical waste the fast path removes.
ROUTINE_BY_CODE: dict[str, str] = {
    "99213": ROUTINE_OFFICE_VISIT,
    "71046": ROUTINE_CHEST_XRAY,
    "80053": ROUTINE_LAB_PANEL,
    "97110": ROUTINE_PT,
    "45378": ROUTINE_COLONOSCOPY,
}


#: Narratives used when the rule engine will hard-stop before necessity is
#: ever judged. The clinical picture is unremarkable on purpose: the case is
#: decided by eligibility, network or benefit facts, not by medicine.
GENERIC_SUPPORTED = """\
Patient with persistent symptoms unresponsive to initial management.
Conservative treatment including physical therapy and anti-inflammatory
medication has been completed without adequate improvement. Examination and
prior imaging support the requested service. Referred for further evaluation
and management.
"""

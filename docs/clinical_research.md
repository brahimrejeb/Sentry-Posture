# Why CVA?

Forward head posture (FHP) is associated with neck pain, tension headaches,
and reduced cervical range of motion. The simplest reliable way to quantify
it is the **craniovertebral angle** (CVA): the angle formed by a horizontal
line through C7 (the prominent vertebra at the base of the neck) and a line
joining C7 to the tragus of the ear. A smaller CVA means the head is
further forward.

Reference values reported in the literature:

- A CVA below ~50° is commonly used as a clinical indicator of FHP in
  adults [^1].
- Office workers with chronic neck pain show a meaningfully smaller CVA
  than asymptomatic peers [^2].

Sentry doesn't try to *diagnose* anything. It uses CVA as a stable,
research-backed scalar that's easy to track, and lets you choose your own
deviation threshold. The defaults — 50° suggested baseline and a 15°
tolerance over a 15-second window — are conservative and adjustable from
the UI.

## Why MediaPipe world landmarks

Pixel-based distance measurements drift whenever the user changes how far
they sit from the camera. MediaPipe's `pose_world_landmarks` provide a
metric 3D estimate that's invariant to camera distance, so the CVA Sentry
computes today is comparable to the one it computed yesterday.

[^1]: Salahzadeh, Z. et al. *Assessment of forward head posture in females:
    observational study.* J Bodywork & Movement Therapies, 2014.
[^2]: Yip, C.H.T. et al. *The relationship between head posture and
    severity and disability of patients with neck pain.* Manual Therapy,
    2008.

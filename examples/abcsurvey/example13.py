"""Example 13 (SAV)
from the survey: "Approval-Based Multi-Winner Voting:
Axioms, Algorithms, and Applications"
by Martin Lackner and Piotr Skowron
"""

from abcvoting import abcrules
from abcvoting.preferences import Profile
from abcvoting import misc
from abcvoting.output import output
from abcvoting.output import DETAILS

output.set_verbosity(DETAILS)

print(misc.header("Example 13", "*"))

# Approval profile
num_cand = 5
a, b, c, d, e = range(5)  # a = 0, b = 1, c = 2, ...
approval_sets = [[a]] + [[b, c, d, e]] * 3
cand_names = "abcde"

profile = Profile(num_cand, cand_names=cand_names)
profile.add_voters(approval_sets)

print(misc.header("Input:"))
print(profile.str_compact())

committees = abcrules.compute_sav(profile, 1)


# verify correctness
assert committees == [{a}]

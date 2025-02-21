"""
Read preflib files (soi, toi, soc or toc)
"""


import os
from abcvoting.preferences import Profile, Voter
from math import ceil
from abcvoting import misc
import ruamel.yaml
from abcvoting.output import output


class PreflibException(Exception):
    pass


def read_preflib_files_from_dir(dir_name, setsize=1, relative_setsize=None):
    """Loads all election files (soi, toi, soc or toc) from the given dir.

    Parameters:
        dir_name: str
            path of directory to be searched for preflib files.

        setsize: int
            Number of top-ranked candidates that voters approve.
            In case of ties, more than setsize candidates are approved.

            Paramer `setsize` is ignored if `relative_setsize` is used.

        relative_setsize: float in (0, 1]
            Indicates which percentage of candidates of the ranking
            are approved (rounded up). In case of ties, more
            candidates are approved.
            E.g., if a voter has 10 candidates and this value is 0.75,
            then the approval set contains the top 8 candidates.

    Returns:
        profiles: dict of str: Profile
            The key is the filename.
    """
    files = get_file_names(dir_name, filename_extensions=[".soi", ".toi", ".soc", ".toc"])

    profiles = {}
    for f in files:
        profile = read_preflib_file(
            os.path.join(dir_name, f), setsize=setsize, relative_setsize=relative_setsize
        )
        profiles[f] = profile
    return profiles


def get_file_names(dir_name, filename_extensions=None):
    """List all file names in a directory that fit the specified filename extensions.
    Does not look into sub-directories.

    Parameters:
        dir_name: str
            path of directory to be searched for files.

        filename_extensions: list of str or None
            file names must match one of these extensions

    Returns:
        files: list of str
            list of file names contained in the directory
    """
    files = []
    for (_, _, filenames) in os.walk(dir_name):
        files = filenames
        break  # do not consider sub-directories
    if len(files) == 0:
        raise FileNotFoundError(f"No files found in {dir_name}")
    if filename_extensions:
        files = [
            f for f in filenames if any(f.endswith(extension) for extension in filename_extensions)
        ]
    return sorted(files)


def _approval_set_from_preflib_datastructures(num_appr, ranking, candidate_map):
    # if num_appr = 1 and the ranking starts with empty set, interpret as empty ballot and
    # return set()
    if (
        num_appr == 1
        and ranking[0].strip()[0] == "{"
        and ranking[0].strip()[-1] == "}"
        and ranking[0].strip().replace("}", "").replace("{", "").strip() == ""
    ):
        return set()

    approval_set = set()
    tied = False
    for i in range(len(ranking)):
        rank = ranking[i].strip()
        if rank.startswith("{"):
            if not tied:
                tied = True
                rank = rank[1:]
            else:
                raise PreflibException("Invalid format for tied candidates: " + str(ranking))
        if rank.endswith("}"):
            if tied:
                tied = False
                rank = rank[:-1]
            else:
                raise PreflibException("Invalid format for tied candidates: " + str(ranking))
        rank = rank.strip()
        if len(rank) > 0:
            try:
                cand = int(rank)
            except ValueError:
                raise PreflibException(f"Expected candidate number but encountered {rank}")
            approval_set.add(cand)
        if len(approval_set) >= num_appr and not tied:
            break
    if tied:
        raise PreflibException("Invalid format for tied candidates: " + str(ranking))
    if len(approval_set) < num_appr:
        # all candidates approved
        approval_set = set(candidate_map.keys())
    return approval_set


def read_preflib_file(filename, setsize=1, relative_setsize=None, use_weights=False):
    """Reads a single preflib file (soi, toi, soc or toc).

    Parameters:

        filename: str
            Name of the preflib file.

        setsize: int
            Number of top-ranked candidates that voters approve.
            In case of ties, more than `setsize` candidates are approved.

            Paramer `setsize` is ignored if `relative_setsize` is used.

        relative_setsize: float in (0, 1]
            Indicates which proportion of candidates of the ranking
            are approved (rounded up). In case of ties, more
            candidates are approved.
            E.g., if a voter has 10 approved candidates and `relative_setsize` is 0.75,
            then the approval set contains the top 8 candidates.

        use_weights: bool
            If False, treat vote count in preflib file as the number of duplicate ballots,
            i.e., the number of voters that have this approval set.
            If True, treat vote count as weight and use this weight in class Voter.

    Returns:
        profile: abcvoting.preferences.Profile
            Preference profile extracted from preflib file,
            including names of candidates
    """
    if setsize <= 0:
        raise ValueError("Parameter setsize must be > 0")
    if relative_setsize and (relative_setsize <= 0.0 or relative_setsize > 1.0):
        raise ValueError("Parameter relative_setsize not in interval (0, 1]")
    with open(filename, "r") as f:
        line = f.readline()
        num_cand = int(line.strip())
        candidate_map = {}
        for _ in range(num_cand):
            parts = f.readline().strip().split(",")
            candidate_map[int(parts[0].strip())] = ",".join(parts[1:]).strip()

        parts = f.readline().split(",")
        try:
            voter_count, _, unique_orders = [int(p.strip()) for p in parts]
        except ValueError:
            raise PreflibException(
                f"Number of voters ill specified ({str(parts)}), should be triple of integers"
            )

        approval_sets = []
        lines = [line.strip() for line in f.readlines() if line.strip()]
        if len(lines) != unique_orders:
            raise PreflibException(
                f"Expected {unique_orders} lines that specify voters in the input, "
                f"encountered {len(lines)}"
            )

    for line in lines:
        parts = line.split(",")
        if len(parts) < 1:
            continue
        try:
            count = int(parts[0])
        except ValueError:
            raise PreflibException(f"Each ranking must start with count/weight ({line})")
        ranking = parts[1:]  # ranking starts after count
        if len(ranking) == 0:
            raise PreflibException("Empty ranking: " + str(line))
        if relative_setsize:
            num_appr = int(ceil(len(ranking) * relative_setsize))
        else:
            num_appr = setsize
        approval_set = _approval_set_from_preflib_datastructures(num_appr, ranking, candidate_map)
        approval_sets.append((count, approval_set))

    # normalize candidates to 0, 1, 2, ...
    cand_names = []
    normalize_map = {}
    for cand in candidate_map.keys():
        cand_names.append(candidate_map[cand])
        normalize_map[cand] = len(cand_names) - 1

    profile = Profile(num_cand, cand_names=cand_names)

    for count, approval_set in approval_sets:
        normalized_approval_set = []
        for cand in approval_set:
            normalized_approval_set.append(normalize_map[cand])
        if use_weights:
            profile.add_voter(Voter(normalized_approval_set, weight=count))
        else:
            profile.add_voters([normalized_approval_set] * count)
    if use_weights:
        if len(profile) != unique_orders:
            raise PreflibException("Number of voters wrongly specified in preflib file.")
    else:
        if len(profile) != voter_count:
            raise PreflibException("Number of voters wrongly specified in preflib file.")
    return profile


def write_profile_to_preflib_toi_file(filename, profile):
    """Writes profile in a preflib toi file

    Parameters:

        filename: str
            File name of the preflib file to be written.

        profile: Profile
            Profile to be written in preflib file.

    Returns:
        None
    """
    with open(filename, "w") as f:
        # write: number of candidates
        f.write(str(profile.num_cand) + "\n")
        # write: names of candidates
        for cand in profile.candidates:
            f.write(f"{cand + 1}, {profile.cand_names[cand]}\n")
        # write: info about number of voters and total weight
        total_weight = sum(voter.weight for voter in profile)
        f.write(f"{total_weight}, {total_weight}, {len(profile)}\n")
        # write: approval sets and weights
        for voter in profile:
            str_approval_set = misc.str_set_of_candidates(
                voter.approved, cand_names=list(range(1, profile.num_cand + 1))
            )
            f.write(f"{voter.weight}, {str_approval_set}\n")


def _yaml_flow_style_list(x):
    yamllist = ruamel.yaml.comments.CommentedSeq(x)
    yamllist.fa.set_flow_style()
    return yamllist


VALID_KEYS = ["profile", "num_cand", "committeesize", "compute", "description"]


def write_abcvoting_instance_to_yaml_file(
    filename, profile, committeesize=None, compute_instances=None, description=None
):
    """Writes abcvoting instance to a yaml file."""
    if not profile.has_unit_weights():
        raise NotImplementedError(
            "write_abcvoting_instance_to_yaml_file() cannot handle " "profiles with weights yet."
        )  # TODO: implement!
    data = {}
    if description is not None:
        data["description"] = description
    data["profile"] = _yaml_flow_style_list([list(voter.approved) for voter in profile])
    data["num_cand"] = profile.num_cand
    if committeesize is not None:
        data["committeesize"] = committeesize
    modified_computed_instances = []
    if compute_instances is not None:
        for compute_instance in compute_instances:
            if "rule_id" not in compute_instance.keys():
                raise ValueError('Each compute instance (dict) requires key "rule_id".')
            mod_compute_instance = {"rule_id": compute_instance["rule_id"]}
            if "result" in compute_instance.keys():
                mod_compute_instance["result"] = _yaml_flow_style_list(
                    [list(committee) for committee in compute_instance["result"]]
                )  # TODO: would be nicer to store committees in set notation (curly braces)
            if "profile" in compute_instance.keys():  # this is superfluous information
                # check that the profile is the same as the main profile
                if str(compute_instance["profile"]) != str(profile):
                    raise ValueError(
                        f"Compute instance contained a profile different from"
                        f"the main profile passed to write_abcvoting_instance_to_yaml_file()."
                    )
            if "committeesize" in compute_instance.keys():  # this is superfluous information
                # check that the profile is the same as the main profile
                if int(compute_instance["committeesize"]) != committeesize:
                    raise ValueError(
                        f"Compute instance contained a committee size different from"
                        f"the committee size passed to write_abcvoting_instance_to_yaml_file()."
                    )
            for key in compute_instance.keys():
                # add other parameters to dictionary
                if key in ["rule_id", "result", "profile", "committeesize"]:
                    continue
                mod_compute_instance[key] = compute_instance[key]
            modified_computed_instances.append(mod_compute_instance)

        data["compute"] = modified_computed_instances

    if not filename.endswith(".abc.yaml"):
        raise ValueError('ABCVoting yaml files should have ".abc.yaml" as filename extension.')

    yaml = ruamel.yaml.YAML()
    yaml.width = 120
    with open(filename, "w") as outfile:
        yaml.dump(data, outfile)


def read_abcvoting_yaml_file(filename):
    """Reads contents of abcvoting yaml file (ending with .abc.yaml)."""
    yaml = ruamel.yaml.YAML(typ="safe", pure=True)
    with open(filename) as inputfile:
        data = yaml.load(inputfile)
    if "profile" not in data.keys():
        raise ValueError(f"{filename} does not contain a profile")
    if "num_cand" in data.keys():
        num_cand = int(data["num_cand"])
    else:
        num_cand = max(cand for approval_set in data["profile"] for cand in approval_set) + 1
    profile = Profile(num_cand)
    profile.add_voters(data["profile"])

    if "committeesize" in data.keys():
        committeesize = int(data["committeesize"])
    else:
        committeesize = None

    if "compute" in data.keys():
        compute_instances = data["compute"]
    else:
        compute_instances = []
    for compute_instance in compute_instances:
        if "rule_id" not in compute_instance.keys():
            raise ValueError('Each rule instance (dict) requires key "rule_id".')
        compute_instance["profile"] = profile
        compute_instance["committeesize"] = committeesize
        if "result" in compute_instance.keys():
            # compute_instance["result"] should be a list of committees (sets)
            compute_instance["result"] = [
                set(committee) for committee in compute_instance["result"]
            ]

    for key in data.keys():
        if key not in VALID_KEYS:
            output.warning(
                f'Reading {filename}: key "{key}" is not valid and consequently ignored.'
            )

    return profile, committeesize, compute_instances, data

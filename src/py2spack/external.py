"""Utilities for converting python packaging requirements to Spack dependency specs.

The code is adapted from Spack/Harmen Stoppels: https://github.com/spack/pypi-to-spack-package.
"""


# TODO: document/comment this code
# TODO: check if everything works as expected

# these python versions are not supported anymore, so we shouldn't need to
# consider them
import re
import sys
from typing import Dict, List, Optional, Union, Any

import packaging.version as pv  # type: ignore
import requests  # type: ignore
import spack.error  # type: ignore
import spack.parser  # type: ignore
import spack.version as sv  # type: ignore
from packaging import markers, specifiers
from spack import spec


UNSUPPORTED_PYTHON = sv.VersionRange(
    sv.StandardVersion.typemin(), sv.StandardVersion.from_string("3.5")
)

NAME_REGEX = re.compile(r"[-_.]+")

LOCAL_SEPARATORS_REGEX = re.compile(r"[\._-]")

# TODO: these are the only known python versions?
KNOWN_PYTHON_VERSIONS = (
    (3, 6, 15),
    (3, 7, 17),
    (3, 8, 18),
    (3, 9, 18),
    (3, 10, 13),
    (3, 11, 7),
    (3, 12, 1),
    (3, 13, 0),
    (4, 0, 0),
)

evalled: Dict = dict()


def acceptable_version(version: str) -> Optional[pv.Version]:
    """Try to parse version string using packaging."""
    try:
        v = pv.parse(version)
        # do not support post releases of prereleases etc.
        if v.pre and (v.post or v.dev or v.local):
            return None
        return v
    except pv.InvalidVersion:
        return None


class JsonVersionsLookup:
    """Class for retrieving available versions of package from PyPI JSON API.

    Caches past requests.
    """

    def __init__(self):
        """Initialize empty JsonVersionsLookup."""
        self.cache: Dict[str, List[pv.Version]] = {}

    def _query(self, name: str) -> List[pv.Version]:
        """Call JSON API."""
        r = requests.get(
            f"https://pypi.org/simple/{name}/",
            headers={"Accept": "application/vnd.pypi.simple.v1+json"},
            timeout=10,
        )
        if r.status_code != 200:
            print(
                f"Json lookup error (pkg={name}): status code {r.status_code}",
                file=sys.stderr,
            )
            if r.status_code == 404:
                print(
                    f"Package {name} not found on PyPI...",
                    file=sys.stderr,
                )
            return []
        versions = r.json()["versions"]
        # parse and sort versions
        return sorted({vv for v in versions if (vv := acceptable_version(v))})

    def _python_versions(self) -> List[pv.Version]:
        """Statically evaluate python versions."""
        return [
            pv.Version(f"{major}.{minor}.{patch}")
            for major, minor, patch in KNOWN_PYTHON_VERSIONS
        ]

    def __getitem__(self, name: str) -> List[pv.Version]:
        """Query cache or API for given package name.

        'python' is evaluated statically.
        """
        result = self.cache.get(name)
        if result is not None:
            return result
        if name == "python":
            result = self._python_versions()
        else:
            result = self._query(name)
        self.cache[name] = result
        return result


def _best_upperbound(
    curr: sv.StandardVersion, nxt: sv.StandardVersion
) -> sv.StandardVersion:
    """Return the most general upper bound that includes curr but not nxt.

    Invariant is that curr < nxt. Here, "most general" means the differentiation should
    happen as high as possible in the version specifier hierarchy.
    """
    assert curr < nxt
    i = 0
    m = min(len(curr), len(nxt))
    # find the first level in the version specifier hierarchy where the two
    # versions differ
    while i < m and curr.version[0][i] == nxt.version[0][i]:
        i += 1

    if i == len(curr) < len(nxt):
        ldiff = len(nxt) - len(curr)
        # e.g. curr = 3.4, nxt = 3.4.5, i = 2
        release, _ = curr.version
        # need to add enough zeros to not include a sub-version by accident (e.g. when
        # curr=2.0, nxt=2.0.0.1)
        release += (0,) * ldiff
        seperators = (".",) * (len(release) - 1) + ("",)
        as_str = ".".join(str(x) for x in release)
        return sv.StandardVersion(
            as_str, (tuple(release), (sv.common.FINAL,)), seperators
        )
    elif i == m:
        return curr  # include pre-release of curr
    else:
        return curr.up_to(i + 1)


def _best_lowerbound(
    prev: sv.StandardVersion, curr: sv.StandardVersion
) -> sv.StandardVersion:
    """Return the most general lower bound that includes curr but not prev.

    Invariant is that prev < curr. Counterpart to _best_upperbound().
    Cases:
        Same length:
            There exists index i s.t. prev[i] < curr[i]. Find i,
            take curr[:i+1] (including i).

        Prev is longer:
            Same as before.

        Curr is longer:
            Either ther exists index i s.t. prev[i] < curr[i],
            or they have the same prefix, then take curr up to the first non-zero index
            after.

    Edge case:
        prereleases, post, dev, local versions: NOT SUPPORTED!
        Semantics of prereleases are tricky.
        E.g. version 1.1-alpha1 is included in range :1.0, but not in range :1.0.0
    """
    assert prev < curr

    # check if prev is a prerelease of curr
    if curr.version[0] == prev.version[0]:
        return curr

    i = 0
    m = min(len(curr), len(prev))
    while i < m:
        if prev.version[0][i] < curr.version[0][i]:
            return curr.up_to(i + 1)
        i += 1

    # both have the same prefix and curr is longer (otherwise we would have found an
    # index i where prev[i] < curr[i], according to invariant)
    assert len(curr) > len(prev)

    # according to invariant, there must be a non-zero value (otherwise the versions
    # would be identical)
    while i < len(curr) and curr.version[0][i] == 0:
        i += 1

    # necessary in order not to exclude relevant prerelease of curr
    # e.g. if prev = 4.2, curr = 4.3-alpha1
    # we want the bound to be 4.3-alpha1, not 4.3
    if i >= len(curr):
        return curr

    return curr.up_to(i + 1)


def packaging_to_spack_version(v: pv.Version) -> sv.StandardVersion:
    """Convert packaging version to equivalent spack version."""
    # TODO: better epoch support.
    release = []
    prerelease = [sv.common.FINAL]
    if v.epoch > 0:
        print(f"warning: epoch {v} isn't really supported", file=sys.stderr)
        release.append(v.epoch)
    release.extend(v.release)
    separators = ["."] * (len(release) - 1)

    if v.pre is not None:
        tp, num = v.pre
        if tp == "a":
            prerelease = [sv.common.ALPHA, num]
        elif tp == "b":
            prerelease = [sv.common.BETA, num]
        elif tp == "rc":
            prerelease = [sv.common.RC, num]
        separators.extend(("-", ""))

        if v.post or v.dev or v.local:
            print(
                f"warning: ignoring post / dev / local version {v}",
                file=sys.stderr,
            )

    else:
        if v.post is not None:
            release.extend((sv.version_types.VersionStrComponent("post"), v.post))
            separators.extend((".", ""))
        if (
            v.dev is not None
        ):  # dev is actually pre-release like, spack makes it a post-release.
            release.extend((sv.version_types.VersionStrComponent("dev"), v.dev))
            separators.extend((".", ""))
        if v.local is not None:
            local_bits = [
                int(i) if i.isnumeric() else sv.version_types.VersionStrComponent(i)
                for i in LOCAL_SEPARATORS_REGEX.split(v.local)
            ]
            release.extend(local_bits)
            separators.append("-")
            separators.extend("." for _ in range(len(local_bits) - 1))

    separators.append("")

    # Reconstruct a string.
    string = ""
    for i, rel in enumerate(release):
        string += f"{rel}{separators[i]}"
    if v.pre:
        string += f"{sv.common.PRERELEASE_TO_STRING[prerelease[0]]}{prerelease[1]}"

    spack_version = sv.StandardVersion(
        string, (tuple(release), tuple(prerelease)), separators
    )

    return spack_version


def _version_type_supported(version: pv.Version) -> bool:
    return (
        version.pre is None
        and version.post is None
        and version.dev is None
        and version.local is None
    )


def condensed_version_list(
    _subset_of_versions: List[pv.Version], _all_versions: List[pv.Version]
) -> sv.VersionList:
    """Create a condensed list of version ranges equivalent to a version subset."""
    # for now, don't support prereleases etc.
    subset_filtered = list(filter(_version_type_supported, _subset_of_versions))
    all_versions_filtered = list(filter(_version_type_supported, _all_versions))

    if len(subset_filtered) < len(_subset_of_versions) or len(
        all_versions_filtered
    ) < len(_all_versions):
        print(
            "Prereleases as well as post, dev, and local versions are not supported",
            "and will be excluded!",
            file=sys.stderr,
        )

    # Sort in Spack's order, which should in principle coincide with
    # packaging's order, but may not in unforseen edge cases.
    subset = sorted(packaging_to_spack_version(v) for v in subset_filtered)
    all_versions = sorted(packaging_to_spack_version(v) for v in all_versions_filtered)

    # Find corresponding index
    i, j = all_versions.index(subset[0]) + 1, 1
    new_versions: List[sv.ClosedOpenRange] = []

    # If the first when entry corresponds to the first known version, use
    # (-inf, ..] as lowerbound.
    if i == 1:
        lo = sv.StandardVersion.typemin()
    else:
        lo = _best_lowerbound(all_versions[i - 2], subset[0])

    while j < len(subset):
        if all_versions[i] != subset[j]:
            hi = _best_upperbound(subset[j - 1], all_versions[i])
            new_versions.append(sv.VersionRange(lo, hi))
            i = all_versions.index(subset[j])
            lo = _best_lowerbound(all_versions[i - 1], subset[j])
        i += 1
        j += 1

    # Similarly, if the last entry corresponds to the last known version,
    # assume the dependency continues to be used: [x, inf).
    if i == len(all_versions):
        hi = sv.StandardVersion.typemax()
    else:
        hi = _best_upperbound(subset[j - 1], all_versions[i])

    new_versions.append(sv.VersionRange(lo, hi))

    vlist = sv.VersionList(new_versions)

    return vlist


def pkg_specifier_set_to_version_list(
    pkg: str,
    specifier_set: specifiers.SpecifierSet,
    version_lookup: JsonVersionsLookup,
) -> sv.VersionList:
    """Convert the specifier set to an equivalent list of version ranges."""
    # TODO: improve how & where the caching is done?
    key = (pkg, specifier_set)
    if key in evalled:
        return evalled[key]
    all_versions = version_lookup[pkg]
    matching = [s for s in all_versions if specifier_set.contains(s, prereleases=True)]
    result = (
        sv.VersionList()
        if not matching
        else condensed_version_list(matching, all_versions)
    )
    evalled[key] = result
    return result


def _eval_python_version_marker(
    variable: str, op: str, value: str, version_lookup: JsonVersionsLookup
) -> Optional[sv.VersionList]:
    # TODO: there might be still some bug caused by python_version vs
    # python_full_version differences.
    # Also `in` and `not in` are allowed, but difficult to get right. They take
    # the rhs as a string and do string matching instead of version parsing...
    # so we don't support them now.
    if op not in ("==", ">", ">=", "<", "<=", "!="):
        return None

    try:
        specifier = specifiers.SpecifierSet(f"{op}{value}")
    except specifiers.InvalidSpecifier:
        print(f"could not parse `{op}{value}` as specifier", file=sys.stderr)
        return None

    return pkg_specifier_set_to_version_list("python", specifier, version_lookup)


def _simplify_python_constraint(versions: sv.VersionList) -> None:
    """Modifies a version list to remove redundant constraints.

    These redundant constraints are implied by UNSUPPORTED_PYTHON. Version list is
    modified in place.
    """
    # First delete everything implied by UNSUPPORTED_PYTHON
    vs = versions.versions
    while vs and vs[0].satisfies(UNSUPPORTED_PYTHON):
        del vs[0]

    if not vs:
        return

    # Remove any redundant lowerbound, e.g. @3.7:3.9 becomes @:3.9 if @:3.6
    # unsupported.
    union = UNSUPPORTED_PYTHON._union_if_not_disjoint(vs[0])
    if union:
        vs[0] = union


def _eval_constraint(
    node: tuple, version_lookup: JsonVersionsLookup
) -> Union[None, bool, List[spec.Spec]]:
    """Evaluate a environment marker (variable, operator, value).

    Returns:
        None: If constraint cannot be evaluated.
        True/False: If constraint is statically true or false.
        List of specs: Spack representation of the constraint(s).
    """
    # TODO: os_name, platform_machine, platform_release, platform_version,
    # implementation_version

    # Operator
    variable, op, value = node

    # Flip the comparison if the value is on the left-hand side.
    if isinstance(variable, markers.Value) and isinstance(value, markers.Variable):
        flipped_op = {
            ">": "<",
            "<": ">",
            ">=": "<=",
            "<=": ">=",
            "==": "==",
            "!=": "!=",
            "~=": "~=",
        }.get(op.value)
        if flipped_op is None:
            print(f"do not know how to evaluate `{node}`", file=sys.stderr)
            return None
        variable, op, value = value, markers.Op(flipped_op), variable

    # print(f"EVAL MARKER {variable.value} {op.value} '{value.value}'")

    # Statically evaluate implementation name, since all we support is cpython
    if (
        variable.value == "implementation_name"
        or variable.value == "platform_python_implementation"
    ):
        if op.value == "==":
            return bool(value.value.lower() == "cpython")
        elif op.value == "!=":
            return bool(value.value.lower() != "cpython")
        return None

    platforms = ("linux", "cray", "darwin", "windows", "freebsd")

    if (
        variable.value == "platform_system" or variable.value == "sys_platform"
    ) and op.value in ("==", "!="):
        platform = value.value.lower()
        if platform == "win32":
            platform = "windows"
        elif platform == "linux2":
            platform = "linux"

        if platform in platforms:
            return [
                spec.Spec(f"platform={p}")
                for p in platforms
                if (p != platform and op.value == "!=")
                or (p == platform and op.value == "==")
            ]
        # TODO: NOTE: in the case of != above, this will return a list of
        # [platform=windows, platform=linux, ...] => this means it is an OR of
        # the list... is this always the case? handled correctly?

        # we don't support it, so statically true/false.
        return bool(op.value == "!=")
    try:
        if variable.value == "extra":
            if op.value == "==":
                return [spec.Spec(f"+{value.value}")]
            elif op.value == "!=":
                return [spec.Spec(f"~{value.value}")]
    except (spack.parser.SpecSyntaxError, ValueError) as e:
        print(f"could not parse `{value}` as variant: {e}", file=sys.stderr)
        return None

    # Otherwise we only know how to handle constraints on the Python version.
    if variable.value not in ("python_version", "python_full_version"):
        return None

    versions = _eval_python_version_marker(
        variable.value, op.value, value.value, version_lookup
    )

    if versions is None:
        return None

    _simplify_python_constraint(versions)

    if not versions:
        # No supported versions for python remain, so statically false.
        return False
    elif versions == sv.any_version:
        # No constraints on python, so statically true.
        return True
    else:
        sp = spec.Spec("^python")
        sp.dependencies("python")[0].versions = versions
        return [sp]


def _eval_node(
    node, version_lookup: JsonVersionsLookup
) -> Union[None, bool, List[spec.Spec]]:
    if isinstance(node, tuple):
        return _eval_constraint(node, version_lookup)
    return _do_evaluate_marker(node, version_lookup)


def _intersection(lhs: List[spec.Spec], rhs: List[spec.Spec]) -> List[spec.Spec]:
    """Compute intersection of spec lists.

    Expand: (a or b) and (c or d) = (a and c) or (a and d) or (b and c) or
    (b and d) where `and` is spec intersection.
    """
    specs: List[spec.Spec] = []
    for expr in lhs:
        for r in rhs:
            intersection = expr.copy()
            try:
                intersection.constrain(r)
            except spack.error.UnsatisfiableSpecError:
                # empty intersection
                continue
            specs.append(intersection)
    return list(set(specs))


def _union(lhs: List[spec.Spec], rhs: List[spec.Spec]) -> List[spec.Spec]:
    """Compute union of spec lists.

    This case is trivial: (a or b) or (c or d) = a or b or c or d, BUT do a
    simplification in case the rhs only expresses constraints on versions.
    """
    if len(rhs) == 1 and not rhs[0].variants and not rhs[0].architecture:
        python, *_ = rhs[0].dependencies("python")
        for expr in lhs:
            expr.versions.add(python.versions)
        return lhs

    return list(set(lhs + rhs))


def _eval_and(group: List, version_lookup):
    lhs = _eval_node(group[0], version_lookup)
    if lhs is False:
        return False

    for node in group[1:]:
        rhs = _eval_node(node, version_lookup)
        if rhs is False:  # false beats none
            return False
        elif lhs is None or rhs is None:  # none beats true / List[Spec]
            lhs = None
        elif rhs is True:
            continue
        elif lhs is True:
            lhs = rhs
        else:  # Intersection of specs
            lhs = _intersection(lhs, rhs)
            if not lhs:  # empty intersection
                return False
    return lhs


def _do_evaluate_marker(
    node: list, version_lookup: JsonVersionsLookup
) -> Union[None, bool, List[spec.Spec]]:
    """Recursively try to evaluate a node (in the marker expression tree).

    A marker is an expression tree, that we can sometimes translate to the
    Spack DSL.
    """
    assert isinstance(node, list) and len(node) > 0, "node assert fails"

    # Inner array is "and", outer array is "or".
    groups = [[node[0]]]
    for i in range(2, len(node), 2):
        op = node[i - 1]
        if op == "or":
            groups.append([node[i]])
        elif op == "and":
            groups[-1].append(node[i])
        else:
            raise ValueError(f"unexpected operator {op}")

    lhs: "bool | List[Any] | None" = _eval_and(groups[0], version_lookup)
    if lhs is True:
        return True
    for group in groups[1:]:
        rhs = _eval_and(group, version_lookup)
        if rhs is True:
            return True
        elif lhs is None or rhs is None:
            lhs = None
        elif lhs is False:
            lhs = rhs
        elif rhs is not False:
            lhs = _union(lhs, rhs)  # type: ignore
    return lhs


def evaluate_marker(
    m: markers.Marker, version_lookup: JsonVersionsLookup
) -> Union[bool, None, List[spec.Spec]]:
    """Evaluate a marker.

    Evaluate the marker expression tree either (1) as a list of specs that constitute
    the when conditions, (2) statically as True or False given that we only support
    cpython, (3) None if we can't translate it into Spack DSL.
    """
    return _do_evaluate_marker(m._markers, version_lookup)

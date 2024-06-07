# Example Python Package
For testing purposes.


### Usage
```python
"""
Example contents of requirements.txt:
-------------------------------------

package1==1.0.0
package2==1.2.3
bad_package_dependency0.0.1
"""

from example_python_package_intern_pyspack.utils import parse_requirements, display_packages
# or
from example_python_package_intern_pyspack import *

path = "path/to/requirements.txt"

packages = parse_requirements(path)
display_packages(packages)


"""
Example Output:
---------------

package1 : 1.0.0
package2 : 1.2.3

Parse Errors:
bad_package_dependency0.0.1
"""
```
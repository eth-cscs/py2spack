import unittest 
import os 

from example_python_package_intern_pyspack import parse_requirements

class TestUtils(unittest.TestCase):

    def test_parse_requirements(self):
        path = "./requirements.txt"
        with open(path, "w+") as f:
            f.write("package1==1.0.0 \npackage2 @ file://some_location\nbad_package1~=1.2.3\nbad_package2 not specified")

        packages = parse_requirements(path)

        expected = {
            "package1": "1.0.0",
            "package2": "file://some_location",
            "bad_package1~=1.2.3": "Parse Error",
            "bad_package2 not specified": "Parse Error"
        }
        os.remove(path)

        self.assertDictEqual(packages, expected)
        
        
if __name__ == "__main__":
    unittest.main()

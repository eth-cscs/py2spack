def parse_requirements(path):
    ''' Parses requirements.txt output from pip freeze '''

    operators = ["==", " @ "]
    
    packages = dict()

    with open(path, "r") as f:
        lines = f.readlines()

    for line in lines:
        parsed = False   

        for op in operators:
            if op in line:

                split_line = line.split(op) 

                if len(split_line) == 2:
                    pkg, version = split_line 
                    packages[pkg.strip()] = version.strip()
                    parsed = True


        if not parsed:
            packages[line.strip()] = "Parse Error"

    return packages

def display_packages(packages: dict):
    ''' Display parsed packages '''

    for pkg, version in packages.items():
        if version == "Parse Error":
            continue
        print(pkg, ":", version)

    failed = [pkg for pkg, version in packages.items() if version == "Parse Error"]
    if failed:
        print("\nParse Errors:")
        for pkg in failed:
            print(pkg)












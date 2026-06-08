import sys
import uuid

def main():
    print(str(uuid.uuid4()), file=sys.stdout)

if __name__ == "__main__":
    main()

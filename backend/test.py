import csv
import sys

def parse_csv():
    with open(file_path, "r", encoding="utf-8-sig") as file:
        reader = csv.DictReader(file)

        print("CSV Columns:")
        print(reader.fieldnames)

        print("\nFirst 5 rows:")
        
        for index, row in enumerate(reader):
                if index == 5:
                    break

        print(row)        

if __name__ == "__main__":
    file_path = "etsy_statement_2026_1.csv"
    parse_csv()
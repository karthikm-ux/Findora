import os
import uuid
from tqdm import tqdm
import sys

# --- Configuration ---

# Total number of unique files to create. 11 Lakh = 1,100,000
TOTAL_UNIQUE_FILES = 1_100_000

# The root directory where all files and subdirectories will be created.
BASE_DIRECTORY = "bplus_tree_test_data"

# How often to create a file with a common name.
# e.g., a value of 100 means a common file will be created for every 100 unique files.
COMMON_FILE_FREQUENCY = 100

# The name of the common file to be created in multiple directories.
COMMON_FILE_NAME = "shared_log.txt"


def generate_files():
    """
    Generates a large number of files within a nested directory structure
    to test file system processing.
    """
    print("--- Test File Generation Utility ---")

    if os.path.exists(BASE_DIRECTORY):
        print(f"Warning: Directory '{BASE_DIRECTORY}' already exists.")
        # Uncomment the line below to exit if the directory exists
        # print("Please remove it or change the BASE_DIRECTORY variable. Exiting.")
        # sys.exit(1)

    # Create the main root directory
    try:
        os.makedirs(BASE_DIRECTORY, exist_ok=True)
        print(f"Base directory '{BASE_DIRECTORY}' created/ensured.")
    except OSError as e:
        print(f"Error creating base directory: {e}")
        sys.exit(1)

    unique_files_created = 0
    common_files_created = 0

    print(f"\nStarting generation of {TOTAL_UNIQUE_FILES:,} unique files...")

    # Use tqdm for a progress bar
    for i in tqdm(range(TOTAL_UNIQUE_FILES), desc="Creating Files", unit="file"):
        # --- 1. Generate path and name for the UNIQUE file ---

        # Format the number as a zero-padded string to create predictable directory names
        # e.g., 123 -> "0000123"
        file_id_str = str(i).zfill(7)

        # Create a two-level directory structure based on the file ID
        # e.g., file "0123456" will go into "BASE_DIRECTORY/01/23/"
        # This prevents putting too many files in a single directory.
        dir_level_1 = file_id_str[0:2]
        dir_level_2 = file_id_str[2:4]
        target_dir = os.path.join(BASE_DIRECTORY, dir_level_1, dir_level_2)

        # Create the directories if they don't exist
        os.makedirs(target_dir, exist_ok=True)

        # Create a unique filename
        unique_filename = f"file_{file_id_str}_{uuid.uuid4().hex[:8]}.data"
        full_path_unique = os.path.join(target_dir, unique_filename)

        # Write some content to the unique file
        try:
            with open(full_path_unique, 'w') as f:
                f.write(f"This is the content for unique file number {i}.\n")
                f.write(f"Full Path: {full_path_unique}\n")
            unique_files_created += 1
        except IOError as e:
            print(f"\nError writing to file {full_path_unique}: {e}")
            continue

        # --- 2. Periodically create a file with a COMMON name ---
        if i % COMMON_FILE_FREQUENCY == 0:
            full_path_common = os.path.join(target_dir, COMMON_FILE_NAME)

            # Write some content to the common file
            try:
                with open(full_path_common, 'w') as f:
                    f.write(f"This is a shared log file.\n")
                    f.write(
                        f"This instance was generated alongside unique file index {i}.\n")
                    f.write(f"Directory: {target_dir}\n")
                common_files_created += 1
            except IOError as e:
                print(f"\nError writing to file {full_path_common}: {e}")
                continue

    # --- 3. Print Summary ---
    print("\n\n--- Generation Complete! ---")
    print(f"Base Directory:          '{os.path.abspath(BASE_DIRECTORY)}'")
    print(f"Unique files created:    {unique_files_created:,}")
    print(f"Common files created:    {
          common_files_created:,} (named '{COMMON_FILE_NAME}')")
    print(f"Total files generated:   {
          unique_files_created + common_files_created:,}")
    print("----------------------------")


if __name__ == "__main__":
    # A simple confirmation before starting, as this can take time and disk space.
    print(f"This script will create ~{TOTAL_UNIQUE_FILES / 1_00_000 + (TOTAL_UNIQUE_FILES /
          COMMON_FILE_FREQUENCY / 1_00_000):.2f} lakh files in the './{BASE_DIRECTORY}/' directory.")
    confirm = input("Are you sure you want to proceed? (y/n): ")
    if confirm.lower() == 'y':
        generate_files()
    else:
        print("Operation cancelled.")

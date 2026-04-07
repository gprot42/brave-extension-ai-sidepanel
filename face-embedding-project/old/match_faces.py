#!/usr/bin/env python3

import os
import argparse
from pathlib import Path
import cv2
import numpy as np
from deepface import DeepFace

def preprocess_image(image_path):
    """Apply histogram equalization to improve image quality."""
    img = cv2.imread(image_path)
    if img is None:
        return None
    # Convert to grayscale and apply histogram equalization
    img_gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
    img_eq = cv2.equalizeHist(img_gray)
    # Convert back to RGB
    img_rgb = cv2.cvtColor(img_eq, cv2.COLOR_GRAY2RGB)
    return img_rgb

def find_and_save_matches(reference_imgs, photo_dir, output_filename, model, threshold=None, detector_backend='retinaface', enforce_detection=True):
    """
    Finds all photos in a directory that contain the person from the reference images.
    Args:
        reference_imgs (list): List of paths to reference images of the person.
        photo_dir (str): Path to the folder containing photos to search through.
        output_filename (str): Name of the file to save the results.
        model (str): Face recognition model (e.g., "ArcFace", "FaceNet", "SFace").
        threshold (float, optional): Custom similarity threshold. Default: None (uses model's default, e.g., 0.68 for ArcFace).
        detector_backend (str): Face detector (e.g., 'retinaface', 'mtcnn', 'opencv'). Default: 'retinaface'.
        enforce_detection (bool): Require face detection in reference images. Default: True.
    """
    # --- 1. Validate Paths ---
    for ref_img in reference_imgs:
        if not Path(ref_img).is_file():
            print(f"❌ Error: Reference image not found at '{ref_img}'")
            return
    if not Path(photo_dir).is_dir():
        print(f"❌ Error: Photo directory not found at '{photo_dir}'")
        return

    # --- 2. Find Matches for Each Reference Image ---
    matching_files = set()
    for ref_img in reference_imgs:
        print(f"🔎 Processing reference image '{ref_img}' with {model} model...")
        try:
            # Preprocess the reference image
            preprocessed_img = preprocess_image(ref_img)
            if preprocessed_img is None:
                print(f"❌ Error: Failed to preprocess '{ref_img}'")
                continue

            # Use DeepFace.find() with preprocessed image
            result_dfs = DeepFace.find(
                img_path=preprocessed_img if preprocessed_img is not None else ref_img,
                db_path=photo_dir,
                model_name=model,
                enforce_detection=enforce_detection,
                silent=True,
                threshold=threshold,
                detector_backend=detector_backend
            )
            matches_df = result_dfs[0]
            if not matches_df.empty:
                matching_files.update(matches_df['identity'].tolist())
        except ValueError as e:
            print(f"❌ Error processing reference image '{ref_img}': {e}")
            continue
        except Exception as e:
            print(f"❌ Unexpected error for '{ref_img}': {e}")
            continue

    # --- 3. Save Results ---
    if not matching_files:
        message = "No matches found for the person."
        print(f"\n✅ {message}")
        with open(output_filename, "w") as f:
            f.write(f"{message}\n")
        return

    try:
        with open(output_filename, "w") as f:
            f.write(f"Found {len(matching_files)} photos containing the person:\n")
            for file_path in sorted(matching_files):
                f.write(f"{os.path.basename(file_path)}\n")
        print(f"\n✅ Success! Found {len(matching_files)} matches. Results saved to '{output_filename}'.")
    except IOError as e:
        print(f"❌ Error writing to output file: {e}")

if __name__ == "__main__":
    # --- Command-Line Arguments ---
    parser = argparse.ArgumentParser(description="Find photos matching a person using DeepFace.")
    parser.add_argument('--reference-imgs', nargs='+', default=["person1.jpg"],
                        help="Paths to reference images (e.g., 'person1.jpg person1_old.jpg') [default: ['person1.jpg']]")
    parser.add_argument('--photo-dir', default="./photos/",
                        help="Folder containing JPEGs to search [default: './photos/']")
    parser.add_argument('--output-file', default="deepface_matches.txt",
                        help="Output file for matching photo names [default: 'deepface_matches.txt']")
    parser.add_argument('--model', default="ArcFace",
                        choices=["ArcFace", "FaceNet", "SFace", "VGG-Face"],
                        help="Face recognition model [default: 'ArcFace']")
    parser.add_argument('--threshold', type=float, default=0.85,
                        help="Similarity threshold (e.g., 0.85 for ArcFace) [default: 0.85]")
    parser.add_argument('--detector-backend', default="retinaface",
                        choices=["retinaface", "mtcnn", "opencv"],
                        help="Face detector backend [default: 'retinaface']")
    parser.add_argument('--enforce-detection', action='store_true',
                        help="Require face detection in reference images [default: False]")

    args = parser.parse_args()

    # --- Run the function ---
    find_and_save_matches(
        reference_imgs=args.reference_imgs,
        photo_dir=args.photo_dir,
        output_filename=args.output_file,
        model=args.model,
        threshold=args.threshold,
        detector_backend=args.detector_backend,
        enforce_detection=args.enforce_detection
    )

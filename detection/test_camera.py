import cv2
import time
import os
from ultralytics import YOLO


def main():
    print("=" * 60)
    print("      VidyaSahayak Camera & YOLO Diagnostic Tool")
    print("=" * 60)

    # 1. Load YOLO Model
    model_path = "yolo11n.pt"
    print(f"Loading YOLO model '{model_path}'...")
    try:
        model = YOLO(model_path)
        print("YOLO model loaded successfully!")
    except Exception as e:
        print(f"Error loading YOLO model: {e}")
        return

    # 2. Open Camera
    camera_idx = int(os.getenv("CAMERA_INDEX", "0"))
    print(f"Opening camera index {camera_idx}...")
    cap = cv2.VideoCapture(camera_idx)

    if not cap.isOpened():
        print(f"\n[ERROR] Could not open camera {camera_idx}!")
        print("Please check if:")
        print("  1. The webcam is physically connected.")
        print(
            "  2. Another application (Zoom, Teams, Browser, OBS) is using the camera."
        )
        print('  3. Try running with $env:CAMERA_INDEX="1" or another index.')
        return

    print("Camera feed opened successfully! Press 'q' in the window to quit.")
    print("-" * 60)

    frame_count = 0
    start_time = time.time()

    while True:
        ret, frame = cap.read()
        if not ret:
            print("Failed to grab frame. Retrying...")
            time.sleep(0.5)
            continue

        frame_count += 1

        # Run YOLO inference
        results = model(frame, verbose=False, device="cpu")

        person_detected = False
        best_conf = 0.0

        for result in results:
            boxes = result.boxes
            for box in boxes:
                # Class 0 is person
                cls = int(box.cls[0].item())
                conf = float(box.conf[0].item())
                if cls == 0:
                    person_detected = True
                    if conf > best_conf:
                        best_conf = conf

                    # Draw green bounding box on screen
                    xyxy = box.xyxy[0].tolist()
                    cv2.rectangle(
                        frame,
                        (int(xyxy[0]), int(xyxy[1])),
                        (int(xyxy[2]), int(xyxy[3])),
                        (0, 255, 0),
                        2,
                    )
                    cv2.putText(
                        frame,
                        f"Person: {conf:.2f}",
                        (int(xyxy[0]), int(xyxy[1]) - 10),
                        cv2.FONT_HERSHEY_SIMPLEX,
                        0.5,
                        (0, 255, 0),
                        2,
                    )

        # Calculate FPS
        elapsed = time.time() - start_time
        fps = frame_count / elapsed if elapsed > 0 else 0.0

        # Display status on frame
        status_text = f"User Detected: {person_detected} (Conf: {best_conf:.2f})"
        status_color = (0, 255, 0) if person_detected else (0, 0, 255)
        cv2.putText(
            frame, status_text, (20, 40), cv2.FONT_HERSHEY_SIMPLEX, 0.7, status_color, 2
        )
        cv2.putText(
            frame,
            f"FPS: {fps:.1f}",
            (20, 70),
            cv2.FONT_HERSHEY_SIMPLEX,
            0.5,
            (255, 255, 255),
            1,
        )

        cv2.imshow("VidyaSahayak - Camera Diagnostic", frame)

        # Log to terminal every 30 frames
        if frame_count % 30 == 0:
            print(
                f"Frame {frame_count} | Person Detected: {person_detected} | Best Conf: {best_conf:.2f} | FPS: {fps:.1f}"
            )

        if cv2.waitKey(1) & 0xFF == ord("q"):
            break

    cap.release()
    cv2.destroyAllWindows()
    print("\nDiagnostic finished. Camera released.")


if __name__ == "__main__":
    main()

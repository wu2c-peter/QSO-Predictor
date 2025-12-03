from PIL import Image

def create_icon():
    try:
        # Load the source image
        img = Image.open("logo.png")
        
        # Windows ICO files usually contain these standard sizes
        icon_sizes = [(256, 256), (128, 128), (64, 64), (48, 48), (32, 32), (16, 16)]
        
        # Save as .ico
        print("Converting logo.png to icon.ico...")
        img.save("icon.ico", format='ICO', sizes=icon_sizes)
        
        print("Success! 'icon.ico' created.")
        
    except FileNotFoundError:
        print("Error: Could not find 'logo.png'. Please save the image first.")
    except Exception as e:
        print(f"Error: {e}")

if __name__ == "__main__":
    create_icon()
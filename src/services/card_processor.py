"""
Card Processing Service
Handles image resizing, PDF creation, and printing
"""
import os
import subprocess
import logging
from PIL import Image
from datetime import datetime

logger = logging.getLogger(__name__)


class CardProcessor:
    """Process card images and generate print-ready PDFs"""

    # CR80 card specifications
    CARD_WIDTH = 1012  # pixels at 300 DPI
    CARD_HEIGHT = 638
    CARD_WIDTH_INCH = 3.375
    CARD_HEIGHT_INCH = 2.125
    DPI = 300

    def __init__(self, upload_folder, output_folder):
        self.upload_folder = upload_folder
        self.output_folder = output_folder
        os.makedirs(upload_folder, exist_ok=True)
        os.makedirs(output_folder, exist_ok=True)

    def resize_image(self, input_path, output_path):
        """
        Resize image to CR80 card dimensions (1012x638 @ 300 DPI)
        """
        logger.info(f"[RESIZE] Processing: {input_path}")

        try:
            img = Image.open(input_path)
            original_size = img.size
            original_mode = img.mode

            # Resize to exact card dimensions
            img = img.resize((self.CARD_WIDTH, self.CARD_HEIGHT), Image.LANCZOS)

            # Convert to RGB if necessary (remove alpha channel for printing)
            if img.mode in ('RGBA', 'P', 'LA'):
                # Create white background for transparency
                background = Image.new('RGB', img.size, (255, 255, 255))
                if img.mode == 'RGBA':
                    background.paste(img, mask=img.split()[3])
                else:
                    img = img.convert('RGB')
                    background = img
                img = background
            elif img.mode != 'RGB':
                img = img.convert('RGB')

            # Save with 300 DPI for correct print size
            img.save(output_path, 'PNG', dpi=(self.DPI, self.DPI))

            logger.info(f"[RESIZE] {original_size} ({original_mode}) -> {img.size} (RGB) @ {self.DPI} DPI")
            return output_path

        except Exception as e:
            logger.error(f"[RESIZE] Error: {e}")
            raise

    def create_card_pdf(self, front_path, back_path, output_path):
        """
        Create a 2-page PDF with exact CR80 page size for duplex printing
        Page 1: Front of card
        Page 2: Back of card
        """
        logger.info(f"[PDF] Creating from: {front_path}, {back_path}")

        try:
            # Use img2pdf command line for reliable page size
            result = subprocess.run(
                [
                    'img2pdf',
                    '--pagesize', f'{self.CARD_WIDTH_INCH}inx{self.CARD_HEIGHT_INCH}in',
                    front_path, back_path,
                    '-o', output_path
                ],
                capture_output=True,
                text=True
            )

            if result.returncode != 0:
                raise Exception(f"img2pdf failed: {result.stderr}")

            file_size = os.path.getsize(output_path)
            logger.info(f"[PDF] Created: {output_path} ({file_size} bytes)")
            return output_path

        except FileNotFoundError:
            logger.error("[PDF] img2pdf not found. Install with: pip install img2pdf")
            raise
        except Exception as e:
            logger.error(f"[PDF] Error: {e}")
            raise

    def create_single_side_pdf(self, image_path, output_path):
        """Create single-page PDF for single-sided cards"""
        logger.info(f"[PDF] Creating single-side from: {image_path}")

        try:
            result = subprocess.run(
                [
                    'img2pdf',
                    '--pagesize', f'{self.CARD_WIDTH_INCH}inx{self.CARD_HEIGHT_INCH}in',
                    image_path,
                    '-o', output_path
                ],
                capture_output=True,
                text=True
            )

            if result.returncode != 0:
                raise Exception(f"img2pdf failed: {result.stderr}")

            return output_path

        except Exception as e:
            logger.error(f"[PDF] Error: {e}")
            raise


class PrintService:
    """Handle sending jobs to the card printer"""

    def __init__(self, printer_name='LXM-Card-Printer', mock_mode=True):
        self.printer_name = printer_name
        self.mock_mode = mock_mode

    def print_card(self, pdf_path, copies=1, duplex=True):
        """
        Send PDF to card printer

        Args:
            pdf_path: Path to the PDF file
            copies: Number of copies to print
            duplex: Enable duplex (double-sided) printing

        Returns:
            dict with success status and job info
        """
        logger.info(f"[PRINT] File: {pdf_path}, Copies: {copies}, Duplex: {duplex}")

        if self.mock_mode:
            logger.info(f"[MOCK] Would print: {pdf_path}")
            return {
                'success': True,
                'mock': True,
                'message': 'Print job queued (MOCK MODE)',
                'job_id': f'MOCK-{datetime.now().strftime("%H%M%S")}'
            }

        # Build lp command
        cmd = ['lp', '-d', self.printer_name, '-n', str(copies)]

        if duplex:
            cmd.extend(['-o', 'DualSidePrinting=Duplex'])

        cmd.append(pdf_path)

        try:
            result = subprocess.run(cmd, capture_output=True, text=True)

            if result.returncode == 0:
                # Extract job ID from output like "request id is LXM-Card-Printer-15"
                job_id = result.stdout.strip()
                logger.info(f"[PRINT] Success: {job_id}")
                return {
                    'success': True,
                    'mock': False,
                    'message': 'Print job sent to printer',
                    'job_id': job_id
                }
            else:
                logger.error(f"[PRINT] Failed: {result.stderr}")
                return {
                    'success': False,
                    'mock': False,
                    'message': f'Print failed: {result.stderr}',
                    'job_id': None
                }

        except Exception as e:
            logger.error(f"[PRINT] Error: {e}")
            return {
                'success': False,
                'mock': False,
                'message': str(e),
                'job_id': None
            }

    def get_printer_status(self):
        """Check if printer is available"""
        try:
            result = subprocess.run(
                ['lpstat', '-p', self.printer_name],
                capture_output=True,
                text=True
            )
            if result.returncode == 0:
                return {
                    'available': True,
                    'status': result.stdout.strip()
                }
            else:
                return {
                    'available': False,
                    'status': result.stderr.strip()
                }
        except Exception as e:
            return {
                'available': False,
                'status': str(e)
            }

    def get_job_status(self, job_id):
        """Get status of a print job"""
        try:
            result = subprocess.run(
                ['lpstat', '-o', self.printer_name],
                capture_output=True,
                text=True
            )
            if job_id in result.stdout:
                return {'status': 'pending', 'in_queue': True}
            else:
                return {'status': 'completed', 'in_queue': False}
        except Exception as e:
            return {'status': 'unknown', 'error': str(e)}

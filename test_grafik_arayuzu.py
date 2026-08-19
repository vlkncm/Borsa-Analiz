import os
import tempfile
import unittest
from pathlib import Path

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtGui import QColor, QPixmap
from PySide6.QtWidgets import QApplication, QSizePolicy

from app_qt import ResponsiveChartLabel


class ResponsiveChartTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QApplication.instance() or QApplication([])

    def test_chart_size_does_not_grow_after_repeated_scaling(self):
        with tempfile.TemporaryDirectory() as tmp:
            image_path = Path(tmp) / "large_chart.png"
            source = QPixmap(2400, 1400)
            source.fill(QColor("#0f172a"))
            self.assertTrue(source.save(str(image_path), "PNG"))

            chart = ResponsiveChartLabel()
            chart.resize(1100, 900)
            self.assertTrue(chart.load_chart(image_path))

            for width in range(1100, 799, -10):
                chart.resize(width, 900)
                self.app.processEvents()
                chart._refresh_pixmap()
                self.assertEqual(chart.height(), ResponsiveChartLabel.CHART_HEIGHT)
                displayed = chart.pixmap()
                self.assertLessEqual(displayed.width(), chart.contentsRect().width())
                self.assertLessEqual(displayed.height(), chart.contentsRect().height())

            self.assertEqual(
                chart.sizePolicy().horizontalPolicy(),
                QSizePolicy.Ignored,
            )
            self.assertEqual(
                chart.sizePolicy().verticalPolicy(),
                QSizePolicy.Fixed,
            )


if __name__ == "__main__":
    unittest.main()

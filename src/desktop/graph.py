"""Interactive native mind map of observed TCP peers."""
from __future__ import annotations

from collections import defaultdict

from PySide6.QtCore import Qt, QRectF
from PySide6.QtGui import QColor, QBrush, QPen, QFont, QPainterPath, QPainter
from PySide6.QtWidgets import QGraphicsView, QGraphicsScene, QGraphicsDropShadowEffect


class ConnectionMap(QGraphicsView):
    def __init__(self):
        super().__init__()
        self.setScene(QGraphicsScene(self))
        self.setRenderHint(QPainter.RenderHint.Antialiasing)
        self.setDragMode(QGraphicsView.DragMode.ScrollHandDrag)
        self.setBackgroundBrush(QColor("#f4f7fb"))
        self.setFrameShape(QGraphicsView.Shape.NoFrame)
        self.setTransformationAnchor(QGraphicsView.ViewportAnchor.AnchorUnderMouse)
        self.setMinimumHeight(330)

    def wheelEvent(self, event):
        factor = 1.15 if event.angleDelta().y() > 0 else 1 / 1.15
        current = self.transform().m11()
        if 0.15 <= current * factor <= 3:
            self.scale(factor, factor)

    def card(self, x, y, title, subtitle, color, width=210):
        path = QPainterPath()
        path.addRoundedRect(QRectF(x, y, width, 66), 12, 12)
        item = self.scene().addPath(path, QPen(QColor("#dce4ef")), QBrush(QColor("#ffffff")))
        item.setToolTip(title + "\n" + subtitle)
        stripe = self.scene().addRect(x, y + 15, 4, 36, QPen(Qt.PenStyle.NoPen), QBrush(QColor(color)))
        name = self.scene().addSimpleText(title[:29], QFont("Segoe UI", 10, QFont.Weight.DemiBold))
        name.setBrush(QColor("#14263d")); name.setPos(x + 16, y + 11)
        description = self.scene().addSimpleText(subtitle[:36], QFont("Segoe UI", 8))
        description.setBrush(QColor("#65788f")); description.setPos(x + 16, y + 36)
        return (x, y, width)

    def edge(self, start, end, color="#bdcfe3"):
        x, y, width = start; ex, ey, _ = end
        path = QPainterPath()
        path.moveTo(x + width, y + 33)
        midpoint = (x + width + ex) / 2
        path.cubicTo(midpoint, y + 33, midpoint, ey + 33, ex, ey + 33)
        item = self.scene().addPath(path, QPen(QColor(color), 2))
        item.setZValue(-1)

    def set_results(self, results, query=""):
        self.scene().clear()
        query = query.casefold().strip()
        rows = []
        for row in results:
            peers = defaultdict(list)
            for connection in row.get("result", {}).get("connections", []):
                peer = connection["remote"]["address"]
                if query and query not in (row["hostname"] + " " + peer + " " + connection["remote"]["port"]).casefold():
                    continue
                peers[peer].append(connection)
            if peers or row.get("status") == "failed":
                rows.append((row, peers))
        if not rows:
            title = "No matching connections" if query else ("No established connections" if results else "No connection snapshot")
            subtitle = "Try another filter" if query else ("Collection returned no established TCP peers" if results else "Select servers and collect connections")
            self.card(80, 100, title, subtitle, "#2c6bed", 360)
            self.fit_map(); return
        y = 0
        anchors = []
        omitted = 0
        for row, peers in rows:
            shown = list(sorted(peers.items()))[:25]
            omitted += max(0, len(peers) - len(shown))
            block_height = max(100, len(shown) * 82)
            host = self.card(350, y + block_height / 2 - 33, row["hostname"],
                             row["ip"] + "  /  " + row["os"], "#2c6bed")
            anchors.append(host)
            if row.get("status") == "failed":
                node = self.card(660, y, "Collection failed", row.get("error", ""), "#d45850", 230)
                self.edge(host, node, "#e9c0bc")
            for index, (peer, connections) in enumerate(shown):
                ports = ", ".join(sorted({item["remote"]["port"] for item in connections}))
                node = self.card(660, y + index * 82, peer,
                                 f"{len(connections)} TCP  /  ports {ports}", "#12a58b", 230)
                self.edge(host, node)
            y += block_height + 45
        center = self.card(20, y / 2 - 55, "ESTABLISHED", f"{len(rows)} selected servers", "#8059d5", 205)
        for anchor in anchors:
            self.edge(center, anchor, "#acc4ef")
        if omitted:
            notice = self.scene().addSimpleText(f"{omitted} peers hidden from map. Use the table or search to inspect them.")
            notice.setPos(20, y + 10)
        self.fit_map()

    def fit_map(self):
        self.scene().setSceneRect(self.scene().itemsBoundingRect().adjusted(-28, -28, 28, 28))
        self.fitInView(self.scene().sceneRect(), Qt.AspectRatioMode.KeepAspectRatio)

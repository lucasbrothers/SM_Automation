"""Interactive native mind map of observed TCP peers."""
from __future__ import annotations

from collections import defaultdict
from desktop.connection_view import snapshot_time

from PySide6.QtCore import Qt, QRectF, QPointF
from PySide6.QtGui import QColor, QBrush, QPen, QFont, QPainterPath, QPainter, QPolygonF
from PySide6.QtWidgets import QGraphicsView, QGraphicsScene


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

    def edge(self, start, end, color="#bdcfe3", ports=""):
        x, y, width = start; ex, ey, _ = end
        path = QPainterPath()
        path.moveTo(x + width, y + 33)
        midpoint = (x + width + ex) / 2
        path.cubicTo(midpoint, y + 33, midpoint, ey + 33, ex, ey + 33)
        item = self.scene().addPath(path, QPen(QColor(color), 2))
        item.setZValue(-1)
        if ports:
            for point, sign in ((QPointF(ex, ey + 33), -1), (QPointF(x + width, y + 33), 1)):
                arrow = QPolygonF([point, QPointF(point.x() + sign * 9, point.y() - 5), QPointF(point.x() + sign * 9, point.y() + 5)])
                self.scene().addPolygon(arrow, QPen(QColor("#2869df")), QBrush(QColor("#2869df")))
            caption = self.scene().addSimpleText(ports.split("\n")[0], QFont("Segoe UI", 8))
            caption.setBrush(QColor("#23344c")); caption.setPos(midpoint - caption.boundingRect().width()/2, (y + ey)/2 + 12)
            caption.setToolTip(ports + "\nBidirectional TCP session; initiator is not known from ESTABLISHED alone.")
            item.setToolTip(ports)

    def set_results(self, results, query=""):
        self.setUpdatesEnabled(False)
        self.scene().setItemIndexMethod(QGraphicsScene.ItemIndexMethod.NoIndex)
        self.scene().clear()
        self.focus_point = None
        query = query.casefold().strip()
        rows = []
        for row in results:
            peers = defaultdict(list)
            for connection in row.get("result", {}).get("connections", []):
                peer = connection["remote"]["address"]
                if query:
                    searchable = f"{row['hostname']} {row['ip']} {connection['local']['address']}:{connection['local']['port']} {peer}:{connection['remote']['port']}"
                    if query not in searchable.casefold():continue
                peers[peer].append(connection)
            if peers or not query or query in (row["hostname"] + " " + row["ip"]).casefold():
                rows.append((row, peers))
        if not rows:
            title = "No matching connections" if query else ("No established connections" if results else "No connection snapshot")
            subtitle = "Try another filter" if query else ("Collection returned no established TCP peers" if results else "Select servers and collect connections")
            self.card(80, 100, title, subtitle, "#2c6bed", 360)
            self.fit_map(); self.setUpdatesEnabled(True); return
        y = 0
        anchors = []
        omitted = 0
        for row, peers in rows:
            warning = row.get("result", {}).get("warning", "")
            shown = list(sorted(peers.items()))[:25]
            omitted += max(0, len(peers) - len(shown))
            block_height = max(100, len(shown) * 82)
            host = self.card(350, y + block_height / 2 - 33, row["hostname"],
                             row["ip"] + "  /  " + row["os"], "#b45309" if warning or row.get("result", {}).get("truncated") else "#2c6bed")
            if row.get("result", {}).get("truncated"):
                notice = self.scene().addSimpleText("Capture limit reached: incomplete snapshot", QFont("Segoe UI", 8))
                notice.setBrush(QColor("#b45309"))
                notice.setPos(host[0], host[1] + 70)
            elif warning:
                notice = self.scene().addSimpleText("Collection warning: hover for details", QFont("Segoe UI", 8))
                notice.setBrush(QColor("#b45309"))
                notice.setToolTip(warning)
                notice.setPos(host[0], host[1] + 70)
            host_time=self.scene().addSimpleText(snapshot_time(row),QFont("Segoe UI",8))
            host_time.setBrush(QColor("#52657b"));host_time.setPos(host[0],host[1]-22)
            anchors.append(host)
            if row.get("status") == "failed":
                node = self.card(660, y, "Collection failed", row.get("error", ""), "#d45850", 230)
                self.edge(host, node, "#e9c0bc")
            elif not shown:
                cancelled = row.get("status") == "cancelled"
                complete = row.get("status") == "completed" and not row.get("result", {}).get("truncated")
                title = "저장 결과 없음 (새로 수집 필요)" if row.get("status")=="not_collected" else "No established connections" if complete else ("Collection cancelled" if cancelled else "Incomplete snapshot")
                node = self.card(660, y, title,
                                 "Successful snapshot / 0 TCP peers" if complete else "No complete connection result",
                                 "#12a58b" if complete else "#b45309", 230)
                self.edge(host, node)
            for index, (peer, connections) in enumerate(shown):
                pairs = sorted({str(item["local"]["port"]) + " ↔ " + str(item["remote"]["port"]) for item in connections})
                ports = ", ".join(pairs)
                node = self.card(660, y + index * 82, peer,
                                 f"{len(connections)} TCP  /  ports {ports}", "#12a58b", 230)
                captions = "\n".join(pairs)
                self.edge(host, node, ports=captions)
            y += block_height + 45
        self.focus_point = QPointF(anchors[0][0]+anchors[0][2]/2, anchors[0][1]+33)
        center = self.card(20, y / 2 - 55, "ESTABLISHED", f"{len(rows)} servers in view", "#8059d5", 205)
        for anchor in anchors:
            self.edge(center, anchor, "#acc4ef")
        if omitted:
            notice = self.scene().addSimpleText(f"{omitted} peers hidden from map. Use the table or search to inspect them.")
            notice.setPos(20, y + 10)
        self.fit_map()
        self.setUpdatesEnabled(True)

    def fit_map(self):
        self.scene().setSceneRect(self.scene().itemsBoundingRect().adjusted(-28, -28, 28, 28))
        self.fitInView(self.scene().sceneRect(), Qt.AspectRatioMode.KeepAspectRatio)
        # Large snapshots must not shrink text into an invisible vertical stripe.
        if self.transform().m11() < .5:
            self.resetTransform(); self.scale(.65,.65)
            self.centerOn(self.focus_point or self.scene().sceneRect().center())

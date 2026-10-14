"""Stable row identities and natural numeric/IP sorting for result tables."""
from PySide6.QtCore import Qt
from PySide6.QtWidgets import QTableWidgetItem, QTreeWidgetItem


from shared.sorting import sort_key

class SortItem(QTableWidgetItem):
    def __lt__(self, other):
        return sort_key(self.text()) < sort_key(other.text())


class SortTreeItem(QTreeWidgetItem):
    def __lt__(self, other):
        column = self.treeWidget().sortColumn()
        return sort_key(self.text(column)) < sort_key(other.text(column))


def enable_sorting(widget):
    widget.horizontalHeader().setSortIndicator(-1, Qt.SortOrder.AscendingOrder)
    widget.setSortingEnabled(True)
    widget.setWordWrap(False)


def row_identity(widget, row=None):
    item = widget.item(widget.currentRow() if row is None else row, 0)
    return item.data(Qt.ItemDataRole.UserRole) if item else None


def populate(widget, rows, identities=None):
    sorting = widget.isSortingEnabled()
    widget.setSortingEnabled(False)
    widget.setRowCount(0)
    widget.setRowCount(len(rows))
    for r, row in enumerate(rows):
        for c, value in enumerate(row):
            text = str(value if value is not None else '')
            item = SortItem(text); item.setToolTip(text)
            if c == 0 and identities is not None:
                item.setData(Qt.ItemDataRole.UserRole, identities[r])
            widget.setItem(r,c,item)
    widget.setSortingEnabled(sorting)

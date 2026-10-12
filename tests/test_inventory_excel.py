from desktop.inventory_excel import save, read_csv
from server.service import inventory_csv

def test_excel_round_trip_preserves_client_fields(tmp_path):
    rows=[{"hostname":"lab","ip":"127.0.0.1","os":"Ubuntu 26.04","profile":"default"}]
    path=tmp_path/'clients.xlsx';save(path,rows)
    assert inventory_csv(read_csv(path))==rows

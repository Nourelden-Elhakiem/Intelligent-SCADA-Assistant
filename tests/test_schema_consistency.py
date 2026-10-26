from pathlib import Path


def test_packaged_schema_matches_root_sql():
    root = Path(__file__).resolve().parents[1]
    def statements(path):
        return [line.strip() for line in path.read_text().splitlines()
                if line.strip() and not line.lstrip().startswith('--')]
    assert statements(root / 'database/schema.sql') == statements(
        root / 'src/intelligent_scada/database/migrations/001_initial.sql')

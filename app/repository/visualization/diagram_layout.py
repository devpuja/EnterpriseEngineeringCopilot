class DiagramLayout:
    def __init__(self, maximum_nodes: int = 30):
        self.maximum_nodes = max(1, maximum_nodes)

    def limit_items(self, items: list[object]) -> tuple[list[object], bool]:
        if len(items) <= self.maximum_nodes:
            return items, False
        return items[:self.maximum_nodes], True

import math
import threading


class Node:
    def __init__(self, order):
        self.order = order
        self.values = []
        self.keys = []
        self.nextKey = None
        self.parent = None
        self.check_leaf = False
        self.lock = threading.Lock()

    # Insert at the leaf
    def insert_at_leaf(self, value, key):
        with self.lock:
            if self.values:
                temp1 = self.values
                for i in range(len(temp1)):
                    if value == temp1[i]:
                        if key not in self.keys[i]:
                            self.keys[i].append(key)
                        break
                    elif value < temp1[i]:
                        self.values = self.values[:i] + [value] + self.values[i:]
                        self.keys = self.keys[:i] + [[key]] + self.keys[i:]
                        break
                    elif i + 1 == len(temp1):
                        self.values.append(value)
                        self.keys.append([key])
                        break
            else:
                self.values = [value]
                self.keys = [[key]]

    def remove_from_leaf(self, value, key=None):
        """
        Removes a specific path (key) or all paths for `value`.
        If the path list for `value` becomes empty, removes `value` from the node.
        Returns True if removed, False otherwise.
        """
        with self.lock:
            for i, val in enumerate(self.values):
                if val == value:
                    if key is None:
                        del self.values[i]
                        del self.keys[i]
                        return True
                    if key in self.keys[i]:
                        self.keys[i].remove(key)
                        if len(self.keys[i]) == 0:
                            del self.values[i]
                            del self.keys[i]
                        return True
                    return False
            return False


# B plus tree
class BplusTree:
    def __init__(self, order=32):
        self.root = Node(order)
        self.root.check_leaf = True
        self.root_lock = threading.Lock()
        self.tree_lock = threading.Lock()

    # Insert operation
    def insert(self, value, key):
        value = str(value)
        with self.tree_lock:
            old_node = self.search(value)
            old_node.insert_at_leaf(value, key)
            with old_node.lock:
                if len(old_node.values) >= old_node.order:
                    node1 = Node(old_node.order)
                    node1.check_leaf = True
                    node1.parent = old_node.parent
                    mid = int(math.ceil(old_node.order / 2)) - 1
                    node1.values = old_node.values[mid + 1:]
                    node1.keys = old_node.keys[mid + 1:]
                    node1.nextKey = old_node.nextKey
                    old_node.values = old_node.values[:mid + 1]
                    old_node.keys = old_node.keys[:mid + 1]
                    old_node.nextKey = node1
                    self.insert_in_parent(old_node, node1.values[0], node1)

    # Remove operation
    def remove(self, value, key=None):
        value = str(value)
        with self.tree_lock:
            leaf_node = self.search(value)
            if leaf_node:
                return leaf_node.remove_from_leaf(value, key)
            return False

    # Search operation for different operations
    def search(self, value) -> Node:
        current_node: Node = self.root
        while not current_node.check_leaf:
            temp2 = current_node.values
            navigated = False
            for i in range(len(temp2)):
                if value == temp2[i]:
                    current_node = current_node.keys[i + 1]
                    navigated = True
                    break
                elif value < temp2[i]:
                    current_node = current_node.keys[i]
                    navigated = True
                    break
                elif i + 1 == len(current_node.values):
                    current_node = current_node.keys[i + 1]
                    navigated = True
                    break
            if not navigated and current_node.keys:
                current_node = current_node.keys[-1]
        return current_node

    def findWithoutKeys(self, value):
        leafNode = self.search(str(value))
        if leafNode:
            for i, item in enumerate(leafNode.values):
                if item == value:
                    return leafNode, i
        return False, -1

    # Find the node
    def find(self, value, key):
        leafNode = self.search(str(value))
        if leafNode:
            for i, item in enumerate(leafNode.values):
                if item == value:
                    if key in leafNode.keys[i]:
                        return True
                    else:
                        return False
        return False

    def get_first_leaf(self) -> Node:
        """Returns the leftmost leaf node in the B+ tree."""
        current_node = self.root
        while not current_node.check_leaf:
            if current_node.keys:
                current_node = current_node.keys[0]
            else:
                break
        return current_node

    def prefix_search(self, prefix: str, limit: int = 100):
        """
        Fast prefix range search using B+ tree leaf linked list traversal.
        Runs in O(log N + K) time.
        """
        prefix = str(prefix)
        leaf = self.search(prefix)
        results = []
        curr = leaf
        while curr:
            for i, val in enumerate(curr.values):
                if val.startswith(prefix):
                    results.append((val, list(curr.keys[i])))
                    if limit and len(results) >= limit:
                        return results
                elif val > prefix and not val.startswith(prefix):
                    return results
            curr = curr.nextKey
        return results

    def substring_search(self, query: str, limit: int = 100):
        """
        Scans leaf nodes sequentially via nextKey for substring matches.
        """
        query = str(query)
        curr = self.get_first_leaf()
        results = []
        while curr:
            for i, val in enumerate(curr.values):
                if query in val:
                    results.append((val, list(curr.keys[i])))
                    if limit and len(results) >= limit:
                        return results
            curr = curr.nextKey
        return results

    def search_query(self, query: str, limit: int = 100):
        """
        Case-insensitive multi-stage search returning:
        1. Exact matches
        2. Prefix matches
        3. Substring matches
        """
        if not query:
            return []
        query_lower = query.lower()
        exact_matches = []
        prefix_matches = []
        substr_matches = []
        seen = set()

        curr = self.get_first_leaf()
        while curr:
            for i, val in enumerate(curr.values):
                val_lower = val.lower()
                if val_lower == query_lower:
                    if val not in seen:
                        seen.add(val)
                        exact_matches.append((val, list(curr.keys[i])))
                elif val_lower.startswith(query_lower):
                    if val not in seen:
                        seen.add(val)
                        prefix_matches.append((val, list(curr.keys[i])))
                elif query_lower in val_lower:
                    if val not in seen:
                        seen.add(val)
                        substr_matches.append((val, list(curr.keys[i])))
            curr = curr.nextKey

        combined = exact_matches + prefix_matches + substr_matches
        if limit:
            return combined[:limit]
        return combined

    def count_total_files(self) -> int:
        """Counts total indexed paths across all leaf nodes."""
        curr = self.get_first_leaf()
        total = 0
        while curr:
            for paths in curr.keys:
                total += len(paths)
            curr = curr.nextKey
        return total

    def count_unique_filenames(self) -> int:
        """Counts total unique filenames indexed in the tree."""
        curr = self.get_first_leaf()
        total = 0
        while curr:
            total += len(curr.values)
            curr = curr.nextKey
        return total

    # Inserting at the parent
    def insert_in_parent(self, n, value, ndash):
        if self.root == n:
            with self.root_lock:
                rootNode = Node(n.order)
                rootNode.values = [value]
                rootNode.keys = [n, ndash]
                self.root = rootNode
                n.parent = rootNode
                ndash.parent = rootNode
                return

        parentNode = n.parent
        temp3 = parentNode.keys
        with parentNode.lock:
            for i in range(len(temp3)):
                if temp3[i] == n:
                    parentNode.values = parentNode.values[:i] + [value] + parentNode.values[i:]
                    parentNode.keys = parentNode.keys[:i + 1] + [ndash] + parentNode.keys[i + 1:]
                    if len(parentNode.keys) > parentNode.order:
                        parentdash = Node(parentNode.order)
                        parentdash.parent = parentNode.parent
                        mid = int(math.ceil(parentNode.order / 2)) - 1
                        parentdash.values = parentNode.values[mid + 1:]
                        parentdash.keys = parentNode.keys[mid + 1:]
                        value_ = parentNode.values[mid]
                        if mid == 0:
                            parentNode.values = parentNode.values[:mid + 1]
                        else:
                            parentNode.values = parentNode.values[:mid]
                        parentNode.keys = parentNode.keys[:mid + 1]
                        for j in parentNode.keys:
                            j.parent = parentNode
                        for j in parentdash.keys:
                            j.parent = parentdash
                        self.insert_in_parent(parentNode, value_, parentdash)


# Print the tree
def printTree(tree):
    # Use Breadth-First Search to print level by level
    queue = [(tree.root, 0)]  # (node, level)
    current_level = -1

    while queue:
        node, level = queue.pop(0)

        if level > current_level:
            if current_level != -1:
                print("\n")
            print(f"Level {level}: ", end="")
            current_level = level

        # Print the values of the current node
        node_type = "Leaf" if node.check_leaf else "Internal"
        print(f"[{node.values}] ({node_type})", end=" ")

        # Enqueue children for the next level if it's an internal node
        if not node.check_leaf:
            for child in node.keys:
                queue.append((child, level + 1))
    print("\n")


if __name__ == "__main__":
    record_len = 3
    bplustree = BplusTree(record_len)
    bplustree.insert('5', '33')
    bplustree.insert('15', '21')
    bplustree.insert('25', '31')
    bplustree.insert('35', '41')
    bplustree.insert('45', '10')

    printTree(bplustree)

    if bplustree.find('5', '34'):
        print("Found")
    else:
        print("Not found")

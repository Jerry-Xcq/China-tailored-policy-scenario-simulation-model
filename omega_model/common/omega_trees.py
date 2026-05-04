"""

**Routines and data structures for tree-based algorithms and functions.**

----

**CODE**

"""

from omega_model import *
import math

class _OMEGATree(OMEGABase):
    """
    Data stucture to hold tree top-level info

    """
    def __init__(self, root_omeganode):
        self.root = root_omeganode
        self.best_path_cost = None


class _OMEGANode(OMEGABase):
    """
    Data structure to hold OMEGATree node info

    """

    def __init__(self, parent_name, name, ghg_credit_bank, vehicle_list, path_cost):
        self.parent_name = parent_name
        self.name = name
        self.ghg_credit_bank = ghg_credit_bank
        self.vehicle_list = vehicle_list
        self.path_cost = path_cost
        # self.stock = None     # do we need to track the entire stock as well?  Or only if PMT affects sales?


class WeightedNode(OMEGABase):
    """
    Implements nodes in a tree where nodes have weights and values.
    Used for drive cycle weighting, but could also be used for weighting in general, if needed.
    ``WeightedNodes`` are stored as node *data* in a ``WeightedTree.tree`` (see below), which is a ``treelib.Tree``.

    """
    def __init__(self, weight):
        """
        Create WeightedNode

        Args:
            weight (numeric): node weight

        """
        self.weight = weight
        self.value = None

    @property
    def weighted_value(self):
        """
        Calculate node weighted value.

        Returns:
            Node weight times node value if weight is not ``None``, else returns 0.

        """
        value = 0

        if self.weight:
            value = self.weight * self.value

        return value

    @property
    def identifier(self):
        """
        Generate a node ID string.

        Returns:
            Node ID string.

        """
        id_str = ''
        try:
            wv = self.weighted_value
            id_str = '%s * %s = %s' % (self.weight, self.value, wv)
        except:
            id_str = '%s' % self.weight
        finally:
            return id_str


import logging
logging.basicConfig(level=logging.DEBUG)

class WeightedTree(OMEGABase):
    """
    Implements a tree data structure of ``WeightedNodes`` and methods of querying node values.

    """
    def __init__(self, tree_df, verbose=False):
        """
        Create WeightedTree from a dataframe containing node connections as column headers and weights as row
        values.

        Args:
            tree_df (DataFrame): a dataframe with column headers such as ``'A->B', 'A->C', 'B->D'`` etc.
            verbose (bool): prints the tree to the console if True

        Note:
            The first element of the first column containing an arrow  (``->``) is taken as the root node.
            Parent nodes must be referenced before child nodes, otherwise there is no particular pre-defined order.
            In the above example, B is a child of A before D can be a child of B.

        """
        from treelib import Tree
        self.tree = Tree()

        for i, c in enumerate(tree_df.columns):
            if '->' in c:
                parent_name, child_name = c.split('->')
                if not self.tree:  # if tree is empty, create root
                    self.tree.create_node(identifier=parent_name, data=WeightedNode(1.0))
                node_weight = tree_df[c].item()
                if type(node_weight) is str:
                    node_weight = Eval.eval(node_weight, {'__builtins__': None}, {})
                self.tree.create_node(identifier=child_name, parent=parent_name, data=WeightedNode(node_weight))
                #如果 node_weight 是 None，它会被直接传递给 WeightedNode

        if verbose:
            self.tree.show(idhidden=False, data_property='weight')

    def leaves(self):
        """
        Get list of tree leaves.

        Returns:
            List of tree nodes (type ``treelib.node.Node``) that have no children.

        """
        return self.tree.leaves()

    def validate_weights(self):
        """
        Validated node weights.
        The sum of a parent node's child node weights must equal 1.0.
        Nodes with a weight of ``None`` are ignored during summation.

        Returns:
            List of node weight errors, or empty list on success.

        """
        import sys

        tree_errors = []

        # validate note weights
        for node_id in self.tree.expand_tree(mode=self.tree.DEPTH):
            child_node_weights = [c.data.weight for c in self.tree.children(node_id)]
            if None in child_node_weights:
                child_node_weights.remove(None)
            if any(child_node_weights):
                child_node_weights = [cnw for cnw in child_node_weights if cnw]  # only validate non-None weights
                if abs(1-sum(child_node_weights)) > sys.float_info.epsilon:
                    tree_errors.append('weight error at %s' % node_id)

        return tree_errors

    @staticmethod
    def calc_node_weighted_value(tree, node_id, weighted=True):
        """
        Calculate node weighted value. 作用是递归计算树中某个节点的加权值，并生成一个对应的公式字符串
        If the node has no children then the weighted value is the node's weighted value, see ``WeightedNode`` above.
        If the node has children then the weighted value is the sum of the weighted values of the children,
        recursively if necessary.当 weighted=True 时，公式字符串会包含当前节点的权重。例如：0.20000000000000000000 * ( ... )。
                                当 weighted=False 时，公式字符串不会包含当前节点的权重，只会用括号包裹子节点的表达式。例如：( ... )
        Args:
            tree (treelib.Tree): the tree to query
            node_id (str): the id of the node to query
            weighted (bool): if ``True`` then return weighted value string, else return node value string

        Returns:
            tuple: (node weighted value, equation string)

        """
        '''if not tree.children(node_id):#递归计算树中某个节点的加权值，并生成一个对应的公式字符串，例如权重0.2，value=100，则加权值=20
            try:#如果当前节点没有子节点（即为叶子节点），直接返回该节点的加权值和公式字符串
                if tree.get_node(node_id).data.weight:#获取当前节点的加权值
                    wv = tree.get_node(node_id).data.weighted_value
                    eq_str = "%.20f * results['%s']" % (tree.get_node(node_id).data.weight, node_id)#公式字符串形如 0.20000000000000000000 * results['A']，用于表达“权重 × 节点值”
                    return wv, eq_str
                else:
                    return 0, '0'
            except:
                raise Exception(
                    '*** Missing drive cycle "%s" in input to WeightedTree.calc_node_weighted_value() ***' %
                    node_id)'''
        
        if not tree.children(node_id):#递归计算树中某个节点的加权值，并生成一个对应的公式字符串，例如权重0.2，value=100，则加权值=20
            try:#如果当前节点没有子节点（即为叶子节点），直接返回该节点的加权值和公式字符串
                weight = tree.get_node(node_id).data.weight
                if weight is not None and not math.isnan(weight):#排除掉 None 和 NaN，但允许权重为 0，只要权重是有效数字（包括0），就会进入主分支；防止Eval.eval() 执行时报 nan 未定义的错误
                    wv = tree.get_node(node_id).data.weighted_value#获取当前节点的加权值
                    eq_str = "%.20f * results['%s']" % (weight, node_id)#公式字符串形如 0.20000000000000000000 * results['A']，用于表达“权重 × 节点值”
                    return wv, eq_str
                else:
                    return 0, '0'
            except:
                raise Exception(
                    '*** Missing drive cycle "%s" in input to WeightedTree.calc_node_weighted_value() ***' %
                    node_id)
        else:#递归处理非叶子节点，即中间的节点
            n = tree.get_node(node_id)#获取当前节点对象
            n.data.value = 0
            if n.data.weight != 1 and n.data.weight is not None and weighted:
                eq_str = '%.20f * (' % n.data.weight#如果当前节点有权重且权重不为 1，并且 weighted=True，则公式字符串以“权重 * (”开头
            else:#；否则只用“(”开头
                eq_str = '('
            for child in tree.children(node_id):#递归处理所有子节点
                wv, child_eq_str = WeightedTree.calc_node_weighted_value(tree, child.identifier)#遍历所有子节点，对每个子节点递归调用 calc_node_weighted_value，得到子节点的加权值和公式字符串
                n.data.value += wv#把子节点的加权值累加到当前节点
                eq_str += '%s + ' % child_eq_str#把子节点的公式字符串拼接到当前节点的公式字符串中
            eq_str = '%s)' % eq_str[0:max(eq_str.rfind(']',), eq_str.rfind(')',))+1]#把公式字符串的最后一个 ] 或 ) 之后的内容截掉，然后加上一个 )，保证公式格式正确
            return n.data.weighted_value, eq_str

    def calc_value(self, values_dict, node_id=None, weighted=False):
        """
        Assign values to tree leaves then calculate the value or weighted value at the given ``node_id`` or at the root
        if no ``node_id`` is provided.  Previously calculated values are cleared first.

        Args:
            values_dict (dict-like): values to assign to leaves
            node_id (str): node id to calculate weighted value of, or tree root if not provided
            weighted (bool): if True then return weighted value, else return node value

        Returns:
            Node (or tree) value (or weighted value)

        """
        '''logging.debug(f"Calculating value for node_id: {node_id}, weighted: {weighted}")
        logging.debug(f"Input values_dict: {values_dict}")'''

        # clear all values 清除所有值
        for n in self.tree.nodes:
            self.tree.get_node(n).data.value = None

        # assign values to leaves
        for key, value in values_dict.items():#values_dict 是一个字典，键是节点ID，值是要赋给节点的新值
            if key in self.tree:#检查树中是否存在这个节点ID
                self.tree.get_node(key).data.value = value#将节点的数据部分的 value 属性更新为新值

        # traverse tree and calculate node values
        if node_id is None:
            node_id = self.tree.root#如果没有指定 node_id，就默认从树的根节点开始遍历

        '''eq_str = WeightedTree.calc_node_weighted_value(self.tree, node_id, weighted)[1]
        try:
            return Eval.eval(eq_str, {'results': values_dict}), eq_str
        except:
            print('omega trees exception !!!')'''
        
        try:
            eq_str = WeightedTree.calc_node_weighted_value(self.tree, node_id, weighted)[1]
            #logging.debug(f"Calculated eq_str: {eq_str}")
            return Eval.eval(eq_str, {'results': values_dict}), eq_str #None 值可能会导致 Eval.eval 抛出异常
        except Exception as e:
            logging.error(f"Exception in calc_value: {e}")
            print(f'omega trees exception !!!: {e}')
            eq_str = "0"  # 设置默认值
            return 0, eq_str  # 返回默认值
        
        '''try:
            eq_str = WeightedTree.calc_node_weighted_value(self.tree, node_id, weighted)[1]
            if eq_str is None:
                # 如果 eq_str 是 None，返回 None
                return None, None
            elif isinstance(eq_str, float) and math.isnan(eq_str):
                # 如果 eq_str 是 NaN，返回 None
                return None, None
            return Eval.eval(eq_str, {'results': values_dict}), eq_str
        except Exception as e:
            logging.error(f"Exception in calc_value: {e}")
            print(f'omega trees exception !!!: {e}')
            return None, None  # 返回 None 表示计算失败'''

    def show(self):
        """
        Print the tree to the console.

        """
        self.tree.show(idhidden=False, data_property='identifier')


if __name__ == "__main__":
    try:
        pass  # TODO: write module test here
    except:
        print("\n#RUNTIME FAIL\n%s\n" % traceback.format_exc())
        sys.exit(-1)

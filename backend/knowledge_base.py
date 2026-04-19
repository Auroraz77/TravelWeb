"""
知识库管理模块 - 简化版 RAG 实现
"""

import os
import re


class SimpleKnowledgeBase:
    """简单的知识库，基于关键词匹配"""

    def __init__(self, knowledge_file: str):
        """初始化知识库"""
        self.knowledge_file = knowledge_file
        self.chunks = []
        self.load_knowledge()

    def load_knowledge(self):
        """加载知识文件并分块"""
        if not os.path.exists(self.knowledge_file):
            print(f"知识文件不存在: {self.knowledge_file}")
            return

        with open(self.knowledge_file, 'r', encoding='utf-8') as f:
            content = f.read()

        # 按标题拆分知识块
        # ## 标题 -> 单个chunk
        pattern = r'(## .+?\n)(.+?)(?=## |$)'
        matches = re.findall(pattern, content, re.DOTALL)

        for title, body in matches:
            chunk = title.strip() + '\n' + body.strip()
            self.chunks.append(chunk)

        print(f"知识库加载完成，共 {len(self.chunks)} 个知识块")

    def retrieve(self, query: str, top_k: int = 2) -> str:
        """
        根据问题检索相关知识块

        Args:
            query: 用户问题
            top_k: 返回最相关的 k 个知识块

        Returns:
            拼接的相关知识文本
        """
        if not self.chunks:
            return ""

        # 简单关键词匹配
        query_words = set(query)
        chunk_scores = []

        for chunk in self.chunks:
            chunk_words = set(chunk)
            # 计算重叠的关键词数量
            overlap = len(query_words & chunk_words)
            chunk_scores.append((overlap, chunk))

        # 按分数排序，取 top_k
        chunk_scores.sort(key=lambda x: x[0], reverse=True)
        retrieved = [chunk for _, chunk in chunk_scores[:top_k]]

        return '\n\n'.join(retrieved)


# 全局知识库实例
_knowledge_base = None


def get_knowledge_base() -> SimpleKnowledgeBase:
    """获取知识库实例"""
    global _knowledge_base
    if _knowledge_base is None:
        knowledge_file = os.path.join(os.path.dirname(__file__), 'knowledge.md')
        _knowledge_base = SimpleKnowledgeBase(knowledge_file)
    return _knowledge_base


def retrieve_knowledge(query: str) -> str:
    """检索相关知识"""
    kb = get_knowledge_base()
    return kb.retrieve(query)

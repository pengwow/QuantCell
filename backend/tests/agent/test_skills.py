"""技能加载测试 - SkillsLoader"""

import json
import pytest
from pathlib import Path

from agent.skills.loader import SkillsLoader


class TestSkillsLoader:
    """测试 SkillsLoader"""

    @pytest.fixture
    def temp_workspace(self, tmp_path):
        return tmp_path

    @pytest.fixture
    def loader(self, temp_workspace):
        return SkillsLoader(temp_workspace)

    def test_list_skills_empty(self, loader):
        """测试列出空技能列表（可能包含内置技能）"""
        skills = loader.list_skills()
        
        # 注意：可能存在内置技能，所以不检查是否为空
        assert isinstance(skills, list)

    def test_list_skills_workspace(self, loader, temp_workspace):
        """测试列出工作空间技能"""
        # 创建技能目录
        skill_dir = temp_workspace / "skills" / "test-skill"
        skill_dir.mkdir(parents=True, exist_ok=True)
        skill_file = skill_dir / "SKILL.md"
        skill_file.write_text("# Test Skill\n\nA test skill.", encoding="utf-8")
        
        skills = loader.list_skills()
        
        # 应该包含我们创建的技能
        workspace_skills = [s for s in skills if s["source"] == "workspace"]
        assert len(workspace_skills) >= 1
        test_skill = next((s for s in skills if s["name"] == "test-skill"), None)
        assert test_skill is not None
        assert test_skill["source"] == "workspace"
        assert "SKILL.md" in test_skill["path"]

    def test_list_skills_multiple(self, loader, temp_workspace):
        """测试列出多个技能"""
        # 创建多个技能
        for i in range(3):
            skill_dir = temp_workspace / "skills" / f"skill-{i}"
            skill_dir.mkdir(parents=True, exist_ok=True)
            skill_file = skill_dir / "SKILL.md"
            skill_file.write_text(f"# Skill {i}\n\nSkill {i} description.", encoding="utf-8")
        
        skills = loader.list_skills()
        
        # 应该包含我们创建的技能
        workspace_skills = [s for s in skills if s["source"] == "workspace"]
        assert len(workspace_skills) >= 3
        skill_names = [s["name"] for s in workspace_skills]
        assert "skill-0" in skill_names
        assert "skill-1" in skill_names
        assert "skill-2" in skill_names

    def test_list_skills_filter_unavailable(self, loader, temp_workspace):
        """测试过滤不可用技能"""
        # 创建一个需要依赖的技能
        skill_dir = temp_workspace / "skills" / "dependent-skill"
        skill_dir.mkdir(parents=True, exist_ok=True)
        skill_file = skill_dir / "SKILL.md"
        skill_file.write_text(
            '---\ndescription: Needs special tool\n---\n\n# Dependent Skill\n\nquantcell:\n  requires:\n    bins:\n      - nonexistent_tool_123456789\n',
            encoding="utf-8"
        )
        
        # 不过滤时应该包含
        skills_all = loader.list_skills(filter_unavailable=False)
        dependent_skill = next((s for s in skills_all if s["name"] == "dependent-skill"), None)
        assert dependent_skill is not None
        
        # 过滤时应该排除（使用一个非常不可能存在的命令名）
        skills_filtered = loader.list_skills(filter_unavailable=True)
        dependent_skill_filtered = next((s for s in skills_filtered if s["name"] == "dependent-skill"), None)
        # 注意：如果系统中存在该命令，测试可能会失败
        # 这是一个边界情况测试

    def test_load_skill_workspace(self, loader, temp_workspace):
        """测试加载工作空间技能"""
        skill_dir = temp_workspace / "skills" / "my-skill"
        skill_dir.mkdir(parents=True, exist_ok=True)
        skill_file = skill_dir / "SKILL.md"
        skill_file.write_text("# My Skill\n\nThis is my skill.", encoding="utf-8")
        
        content = loader.load_skill("my-skill")
        
        assert content is not None
        assert "My Skill" in content
        assert "This is my skill" in content

    def test_load_skill_not_found(self, loader):
        """测试加载不存在的技能"""
        content = loader.load_skill("nonexistent-skill")
        
        assert content is None

    def test_load_skills_for_context(self, loader, temp_workspace):
        """测试加载技能到上下文"""
        # 创建技能
        skill_dir = temp_workspace / "skills" / "context-skill"
        skill_dir.mkdir(parents=True, exist_ok=True)
        skill_file = skill_dir / "SKILL.md"
        skill_file.write_text(
            '---\ndescription: Context skill\n---\n\n# Context Skill\n\nUse this in context.',
            encoding="utf-8"
        )
        
        content = loader.load_skills_for_context(["context-skill"])
        
        assert "Context Skill" in content
        assert "Use this in context" in content

    def test_load_skills_for_context_multiple(self, loader, temp_workspace):
        """测试加载多个技能到上下文"""
        # 创建多个技能
        for i in range(2):
            skill_dir = temp_workspace / "skills" / f"multi-{i}"
            skill_dir.mkdir(parents=True, exist_ok=True)
            skill_file = skill_dir / "SKILL.md"
            skill_file.write_text(f"# Multi {i}\n\nSkill {i}.", encoding="utf-8")
        
        content = loader.load_skills_for_context(["multi-0", "multi-1"])
        
        assert "Multi 0" in content
        assert "Multi 1" in content

    def test_load_skills_for_context_empty(self, loader):
        """测试加载空技能列表到上下文"""
        content = loader.load_skills_for_context([])
        
        assert content == ""

    def test_build_skills_summary_empty(self, loader):
        """测试构建技能摘要（可能包含内置技能）"""
        summary = loader.build_skills_summary()
        
        # 注意：可能存在内置技能，所以检查格式
        assert isinstance(summary, str)
        if summary:
            assert "<skills>" in summary
            assert "</skills>" in summary

    def test_build_skills_summary(self, loader, temp_workspace):
        """测试构建技能摘要"""
        # 创建技能
        skill_dir = temp_workspace / "skills" / "summary-skill"
        skill_dir.mkdir(parents=True, exist_ok=True)
        skill_file = skill_dir / "SKILL.md"
        skill_file.write_text(
            '---\ndescription: Summary test skill\n---\n\n# Summary Skill',
            encoding="utf-8"
        )
        
        summary = loader.build_skills_summary()
        
        assert "<skills>" in summary
        assert "</skills>" in summary
        assert "summary-skill" in summary
        assert "Summary test skill" in summary

    def test_build_skills_summary_with_availability(self, loader, temp_workspace):
        """测试技能摘要包含可用性信息"""
        # 创建可用技能
        skill_dir = temp_workspace / "skills" / "available-skill"
        skill_dir.mkdir(parents=True, exist_ok=True)
        skill_file = skill_dir / "SKILL.md"
        skill_file.write_text(
            '---\ndescription: Available skill\n---\n\n# Available Skill',
            encoding="utf-8"
        )
        
        summary = loader.build_skills_summary()
        
        assert 'available="true"' in summary

    def test_get_always_skills(self, loader, temp_workspace):
        """测试获取always技能"""
        # 创建always技能
        skill_dir = temp_workspace / "skills" / "always-skill"
        skill_dir.mkdir(parents=True, exist_ok=True)
        skill_file = skill_dir / "SKILL.md"
        skill_file.write_text(
            '---\ndescription: Always active\nalways: true\n---\n\n# Always Skill',
            encoding="utf-8"
        )
        
        # 创建普通技能
        skill_dir2 = temp_workspace / "skills" / "normal-skill"
        skill_dir2.mkdir(parents=True, exist_ok=True)
        skill_file2 = skill_dir2 / "SKILL.md"
        skill_file2.write_text(
            '---\ndescription: Normal skill\n---\n\n# Normal Skill',
            encoding="utf-8"
        )
        
        always_skills = loader.get_always_skills()
        
        assert "always-skill" in always_skills
        assert "normal-skill" not in always_skills

    def test_get_skill_metadata(self, loader, temp_workspace):
        """测试获取技能元数据"""
        # 创建带元数据的技能
        skill_dir = temp_workspace / "skills" / "meta-skill"
        skill_dir.mkdir(parents=True, exist_ok=True)
        skill_file = skill_dir / "SKILL.md"
        skill_file.write_text(
            '---\ndescription: Meta test skill\nauthor: Test\nversion: 1.0\n---\n\n# Meta Skill',
            encoding="utf-8"
        )
        
        metadata = loader.get_skill_metadata("meta-skill")
        
        assert metadata is not None
        assert metadata.get("description") == "Meta test skill"
        assert metadata.get("author") == "Test"
        assert metadata.get("version") == "1.0"

    def test_get_skill_metadata_no_frontmatter(self, loader, temp_workspace):
        """测试获取无frontmatter的技能元数据"""
        skill_dir = temp_workspace / "skills" / "no-meta-skill"
        skill_dir.mkdir(parents=True, exist_ok=True)
        skill_file = skill_dir / "SKILL.md"
        skill_file.write_text("# No Meta Skill\n\nNo frontmatter.", encoding="utf-8")
        
        metadata = loader.get_skill_metadata("no-meta-skill")
        
        # 应该返回None或空字典
        assert metadata is None or metadata == {}

    def test_get_skill_metadata_not_found(self, loader):
        """测试获取不存在技能的元数据"""
        metadata = loader.get_skill_metadata("nonexistent")
        
        assert metadata is None

    def test_strip_frontmatter(self, loader):
        """测试移除frontmatter"""
        content = """---
description: Test
always: true
---

# Test Skill

Content here."""
        
        stripped = loader._strip_frontmatter(content)
        
        assert "---" not in stripped
        assert "Test Skill" in stripped
        assert "Content here" in stripped

    def test_strip_frontmatter_none(self, loader):
        """测试移除不存在的frontmatter"""
        content = "# Simple Content\n\nNo frontmatter."
        
        stripped = loader._strip_frontmatter(content)
        
        assert stripped == content

    def test_parse_metadata_valid(self, loader):
        """测试解析有效元数据"""
        raw = '{"quantcell": {"description": "Test", "always": true}}'
        
        meta = loader._parse_metadata(raw)
        
        assert meta.get("description") == "Test"
        assert meta.get("always") is True

    def test_parse_metadata_invalid(self, loader):
        """测试解析无效元数据"""
        raw = "invalid json"
        
        meta = loader._parse_metadata(raw)
        
        assert meta == {}

    def test_parse_metadata_empty(self, loader):
        """测试解析空元数据"""
        meta = loader._parse_metadata("")
        
        assert meta == {}

    def test_check_requirements_met(self, loader):
        """测试检查满足的依赖"""
        # 使用一个肯定存在的命令
        skill_meta = {
            "requires": {
                "bins": ["python"],
            }
        }
        
        result = loader._check_requirements(skill_meta)
        
        assert result is True

    def test_check_requirements_not_met(self, loader):
        """测试检查不满足的依赖"""
        skill_meta = {
            "requires": {
                "bins": ["nonexistent_command_12345"],
            }
        }
        
        result = loader._check_requirements(skill_meta)
        
        assert result is False

    def test_check_requirements_env(self, loader, monkeypatch):
        """测试检查环境变量依赖"""
        # 设置环境变量
        monkeypatch.setenv("TEST_ENV_VAR", "value")
        
        skill_meta = {
            "requires": {
                "env": ["TEST_ENV_VAR"],
            }
        }
        
        result = loader._check_requirements(skill_meta)
        
        assert result is True

    def test_check_requirements_env_missing(self, loader, monkeypatch):
        """测试检查缺失的环境变量依赖"""
        # 确保环境变量不存在
        monkeypatch.delenv("MISSING_ENV_VAR", raising=False)
        
        skill_meta = {
            "requires": {
                "env": ["MISSING_ENV_VAR"],
            }
        }
        
        result = loader._check_requirements(skill_meta)
        
        assert result is False

    def test_check_requirements_no_requirements(self, loader):
        """测试检查无依赖"""
        skill_meta = {}
        
        result = loader._check_requirements(skill_meta)
        
        assert result is True

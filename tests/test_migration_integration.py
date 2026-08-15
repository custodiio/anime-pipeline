"""
Testes de Integração e Verificação — Ecossistema Central AnimeRecap
Valida a saúde, conexões ao Neon PostgreSQL e inicialização de todos os módulos.
"""

import os
import sys
import unittest
from pathlib import Path
from dotenv import load_dotenv

# Carrega .env
ROOT_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT_DIR))
load_dotenv(ROOT_DIR / ".env")

if sys.platform == "win32":
    try:
        sys.stdout.reconfigure(encoding="utf-8")
        sys.stderr.reconfigure(encoding="utf-8")
    except Exception:
        pass



class TestAnimeRecapEcosystem(unittest.TestCase):

    def test_01_neon_connection(self):
        """Valida a conexão singleton com o banco PostgreSQL Neon."""
        from shared.db_connection import DBConnectionContext
        with DBConnectionContext(autocommit=True) as conn:
            self.assertIsNotNone(conn)
            with conn.cursor() as cur:
                cur.execute("SELECT 1;")
                res = cur.fetchone()
                self.assertEqual(res[0], 1)
        print("✅ [TEST] Conexão PostgreSQL Neon: OK")

    def test_02_scrapper_database_methods(self):
        """Valida métodos CRUD do Scrapper Douyin no PostgreSQL Neon."""
        from scrapper import database
        
        # Teste de canais
        database.add_channel(uid="test_uid_999", name="Canal Teste", content_type="anime")
        channels = database.get_channels(content_type="anime")
        channel_uids = [c["uid"] for c in channels]
        self.assertIn("test_uid_999", channel_uids)
        
        # Teste de limpeza do canal de teste
        database.remove_channel("test_uid_999")
        
        # Teste de termos de busca
        terms = database.get_search_terms()
        self.assertTrue(len(terms) >= 2)
        print("✅ [TEST] Scrapper Douyin Database (Neon): OK")

    def test_03_scrapper_fastapi_app(self):
        """Valida que a API FastAPI do Scrapper Douyin carrega e responde."""
        from scrapper.web_panel import app
        from fastapi.testclient import TestClient
        
        client = TestClient(app)
        response = client.get("/api/douyin/collections")
        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertTrue(data.get("ok"))
        print("✅ [TEST] Scrapper Douyin FastAPI: OK")

    def test_04_postrecap_db_methods(self):
        """Valida o módulo de banco de dados do Post Recap."""
        from post_recap import db
        
        # Teste de agendamento de post
        post_id = db.add_scheduled_post(
            video_path="temp/test.mp4",
            thumbnail_youtube="temp/thumb_yt.jpg",
            thumbnail_tiktok="temp/thumb_tt.jpg",
            title_youtube="Título Teste",
            title_shorts="Shorts Teste",
            tiktok_caption="#anime #recap",
            instagram_caption="Legenda Insta",
            post_youtube=True,
            post_shorts=True,
            post_tiktok=False,
            post_instagram=False,
            tiktok_privacy="public",
            scheduled_time="2099-01-01 12:00:00",
            shorts_description="Desc teste"
        )
        self.assertIsNotNone(post_id)
        
        # Deleta post de teste
        deleted = db.delete_scheduled_post(post_id)
        self.assertIsNotNone(deleted)
        print("✅ [TEST] Post Recap DB (Neon): OK")

    def test_05_tiktok_approval_db_and_api(self):
        """Valida a API FastAPI e a verificação de aprovação do TikTok Approval."""
        from tiktok_approval import db_helper
        from tiktok_approval.main import app
        from fastapi.testclient import TestClient
        
        # Usuário novo deve iniciar desaprovado
        test_email = "tester_novo_auto@teste.com"
        approved = db_helper.check_user_approval(test_email)
        self.assertFalse(approved, "Usuário novo deve ser pendente (não aprovado)")
        
        # Teste via endpoint check-approval
        client = TestClient(app)
        resp = client.post("/api/auth/check-approval", json={"email": test_email})
        self.assertEqual(resp.status_code, 200)
        self.assertFalse(resp.json().get("approved"))
        
        # Limpeza do usuário de teste
        from shared.db_connection import DBConnectionContext
        with DBConnectionContext(autocommit=True) as conn:
            with conn.cursor() as cur:
                cur.execute("DELETE FROM tiktok_approved_users WHERE email = %s", (test_email,))
                
        print("✅ [TEST] TikTok Approval API & Regra de Segurança: OK")

    def test_06_kuma_recap_components(self):
        """Valida imports e status do Kuma Recap."""
        from bot.database import get_running_projects
        projects = get_running_projects()
        self.assertIsInstance(projects, list)
        print("✅ [TEST] Kuma Recap Components: OK")

if __name__ == "__main__":
    unittest.main()

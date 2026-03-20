"""
Main Telegram Bot - All handlers and command routing
"""
import os
import uuid
import asyncio
import re
from pathlib import Path
from loguru import logger

from telegram import Update, InlineKeyboardMarkup, InlineKeyboardButton
from telegram.ext import (
    Application, CommandHandler, MessageHandler,
    CallbackQueryHandler, filters, ContextTypes,
)
from telegram.constants import ParseMode, ChatAction

from config import get_settings
from core.extractor import ConceptExtractor
from core.parser import DocumentParser
from services.graph_service import GraphService
from services.vector_service import VectorService
from services.visualization import VisualizationService

settings = get_settings()

E = {
    "brain": "🧠", "graph": "🕸️", "doc": "📄", "search": "🔍",
    "gap": "🔬", "path": "🛤️", "stats": "📊", "trash": "🗑️",
    "ok": "✅", "err": "❌", "warn": "⚠️", "spark": "✨",
    "rocket": "🚀", "wait": "⏳", "list": "📋", "arrow": "→",
    "fire": "🔥", "bulb": "💡", "node": "🔵", "edge": "🔗",
}

WELCOME_MSG = f"""
{E['brain']} *Knowledge Graph Builder Bot*

Transform your research into an intelligent, explorable knowledge graph!

*What I can do:*
{E['doc']} Analyze PDFs, documents & research notes
{E['graph']} Build interactive knowledge graphs
{E['search']} Semantic search across your documents  
{E['gap']} Detect research gaps (PhD-level!)
{E['path']} Explain concept pathways
{E['stats']} Show graph statistics & insights

*Commands:*
/graph — View your knowledge graph
/analyze — Analyze graph structure
/path source → target — Find concept path
/gaps — Detect research gaps
/search query — Search your knowledge
/nodes — List all concepts
/clear — Reset your knowledge graph
/help — Show this help

*Just send me:*
• Any text (research notes, abstracts)
• PDF files
• Word documents (.docx)
• Images with text (OCR)

{E['rocket']} Let's build your research brain!
"""


class KnowledgeGraphBot:
    """Main bot class"""

    def __init__(self):
        self.extractor = ConceptExtractor()
        self.parser = DocumentParser()
        self.graph_svc = GraphService()
        self.vector_svc = VectorService()
        self.viz_svc = VisualizationService()
        self.app = None

    async def post_init(self, application: Application) -> None:
        """Connect services after the Application is initialized."""
        logger.info("Connecting to databases...")
        await self.graph_svc.connect()
        await self.vector_svc.connect()
        logger.success("All services connected")

    async def post_shutdown(self, application: Application) -> None:
        """Close services after the Application is stopped."""
        logger.info("Closing bot services...")
        await self.graph_svc.close()
        await self.vector_svc.close()

    def run(self):
        """Start the bot using the official blocking run_polling()"""
        Path("graphs").mkdir(exist_ok=True)
        Path("logs").mkdir(exist_ok=True)

        self.app = (
            Application.builder()
            .token(settings.telegram_bot_token)
            .post_init(self.post_init)
            .post_shutdown(self.post_shutdown)
            .build()
        )
        self._register_handlers()
        logger.info("🚀 Starting bot polling via run_polling()...")
        self.app.run_polling(drop_pending_updates=True)

    def _register_handlers(self):
        app = self.app
        app.add_handler(CommandHandler("start", self.cmd_start))
        app.add_handler(CommandHandler("help", self.cmd_start))
        app.add_handler(CommandHandler("graph", self.cmd_graph))
        app.add_handler(CommandHandler("analyze", self.cmd_analyze))
        app.add_handler(CommandHandler("gaps", self.cmd_gaps))
        app.add_handler(CommandHandler("path", self.cmd_path))
        app.add_handler(CommandHandler("search", self.cmd_search))
        app.add_handler(CommandHandler("nodes", self.cmd_nodes))
        app.add_handler(CommandHandler("clear", self.cmd_clear))
        app.add_handler(MessageHandler(filters.Document.ALL, self.handle_document))
        app.add_handler(MessageHandler(filters.PHOTO, self.handle_photo))
        app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, self.handle_text))
        app.add_handler(CallbackQueryHandler(self.handle_callback))
        logger.info("Handlers registered")

    # ─── Commands ────────────────────────────────────────────────────────────

    async def cmd_start(self, update: Update, ctx: ContextTypes.DEFAULT_TYPE):
        await (update.message or update.callback_query.message).reply_text(
            WELCOME_MSG, parse_mode=ParseMode.MARKDOWN
        )

    async def cmd_graph(self, update: Update, ctx: ContextTypes.DEFAULT_TYPE):
        user_id = update.effective_user.id
        msg = update.message or update.callback_query.message
        await msg.reply_chat_action(ChatAction.TYPING)

        graph_data = await self.graph_svc.get_user_graph(user_id)
        nodes, rels = graph_data["nodes"], graph_data["relationships"]

        if not nodes:
            await msg.reply_text(f"{E['warn']} Your graph is empty! Send research text.")
            return

        await msg.reply_text(f"{E['wait']} Generating graph ({len(nodes)} concepts)...")
        png_path = await self.viz_svc.generate_png(user_id, nodes, rels, title="Your Graph")

        if png_path and Path(png_path).exists():
            with open(png_path, "rb") as f:
                caption = f"{E['graph']} *Your Knowledge Graph*\n{len(nodes)} concepts | {len(rels)} relationships"
                keyboard = InlineKeyboardMarkup([
                    [InlineKeyboardButton(f"{E['spark']} Refresh", callback_data="refresh_graph")],
                    [InlineKeyboardButton(f"{E['gap']} Research Gaps", callback_data="find_gaps")],
                    [InlineKeyboardButton(f"{E['stats']} Analysis", callback_data="analyze")],
                ])
                await msg.reply_photo(photo=f, caption=caption, parse_mode=ParseMode.MARKDOWN, reply_markup=keyboard)
            try: os.remove(png_path)
            except Exception: pass
        else:
            await msg.reply_text(f"{E['err']} Error generating graph.")

    async def cmd_analyze(self, update: Update, ctx: ContextTypes.DEFAULT_TYPE):
        user_id = update.effective_user.id
        msg = update.message or update.callback_query.message
        await msg.reply_chat_action(ChatAction.TYPING)
        structure = await self.graph_svc.analyze_graph_structure(user_id)
        stats = structure.get("stats", {})
        if not stats.get("total_nodes"):
            await msg.reply_text(f"{E['warn']} No graph data yet.")
            return
        hubs = "\n".join(f"• `{h['name']}` ({h['degree']} conn)" for h in structure.get("hubs", [])) or "None"
        msg_text = f"{E['stats']} *Graph Analysis*\nNodes: `{stats.get('total_nodes',0)}` | Edges: `{stats.get('total_edges',0)}`"
        await msg.reply_text(msg_text, parse_mode=ParseMode.MARKDOWN)

    async def cmd_gaps(self, update: Update, ctx: ContextTypes.DEFAULT_TYPE):
        user_id = update.effective_user.id
        msg = update.message or update.callback_query.message
        await msg.reply_chat_action(ChatAction.TYPING)
        graph_data = await self.graph_svc.get_user_graph(user_id)
        if not graph_data["nodes"]:
            await msg.reply_text(f"{E['warn']} Build your graph first!")
            return
        await msg.reply_text(f"{E['wait']} Analyzing research gaps...")
        domain = graph_data["nodes"][0].get("domain", "Research")
        gaps = await self.extractor.find_research_gaps(graph_data["nodes"], graph_data["relationships"], domain)
        gap_text = "\n\n".join(f"🔴 *{g.get('title')}*\n_{g.get('description', '')}_" for g in gaps.get("gaps", [])[:3]) or "No gaps found!"
        await msg.reply_text(f"{E['gap']} *Gaps Analysis*\n\n{gap_text}", parse_mode=ParseMode.MARKDOWN)

    async def cmd_path(self, update: Update, ctx: ContextTypes.DEFAULT_TYPE):
        user_id, text = update.effective_user.id, (update.message.text if update.message else "")
        msg = update.message or update.callback_query.message
        match = re.search(r"/path\s+(.+?)\s*[→>]\s*(.+)", text, re.IGNORECASE)
        if not match:
            await msg.reply_text(f"{E['path']} Usage: `/path Source → Target`")
            return
        source, target = match.group(1).strip(), match.group(2).strip()
        await msg.reply_chat_action(ChatAction.TYPING)
        paths = await self.graph_svc.find_path(user_id, source, target)
        if not paths:
            await msg.reply_text(f"{E['warn']} No path found.")
            return
        await msg.reply_text(f"{E['path']} Found connection path between `{source}` and `{target}`!")

    async def cmd_search(self, update: Update, ctx: ContextTypes.DEFAULT_TYPE):
        user_id, query = update.effective_user.id, " ".join((update.message.text if update.message else "").split()[1:])
        msg = update.message or update.callback_query.message
        if not query:
            await msg.reply_text(f"{E['search']} Usage: `/search your query`")
            return
        await msg.reply_chat_action(ChatAction.TYPING)
        concepts = await self.graph_svc.search_concepts(user_id, query)
        docs = await self.vector_svc.semantic_search(user_id, query)
        await msg.reply_text(f"{E['search']} *Results:*\nConcepts: {len(concepts)} | Docs: {len(docs)}", parse_mode=ParseMode.MARKDOWN)

    async def cmd_nodes(self, update: Update, ctx: ContextTypes.DEFAULT_TYPE):
        msg = update.message or update.callback_query.message
        graph_data = await self.graph_svc.get_user_graph(update.effective_user.id)
        nodes = graph_data["nodes"]
        if not nodes:
            await msg.reply_text("No concepts yet.")
            return
        msg_text = f"{E['list']} *Concepts:* " + ", ".join(f"`{n['name']}`" for n in nodes[:20])
        await msg.reply_text(msg_text, parse_mode=ParseMode.MARKDOWN)

    async def cmd_clear(self, update: Update, ctx: ContextTypes.DEFAULT_TYPE):
        msg = update.message or update.callback_query.message
        keyboard = InlineKeyboardMarkup([[InlineKeyboardButton("Clear", callback_data="confirm_clear"), InlineKeyboardButton("Cancel", callback_data="cancel_clear")]])
        await msg.reply_text(f"{E['warn']} *Are you sure?*", parse_mode=ParseMode.MARKDOWN, reply_markup=keyboard)

    async def handle_text(self, update: Update, ctx: ContextTypes.DEFAULT_TYPE):
        user_id, text = update.effective_user.id, update.message.text.strip()
        if len(text) < 50:
            await update.message.reply_text(f"{E['warn']} Send more content.")
            return
        await self._process_content(update, user_id, text, "text_input.txt")

    async def handle_document(self, update: Update, ctx: ContextTypes.DEFAULT_TYPE):
        user_id, doc = update.effective_user.id, update.message.document
        filename = doc.file_name or "document"
        status = await update.message.reply_text(f"{E['doc']} Processing `{filename}`...")
        try:
            file = await ctx.bot.get_file(doc.file_id)
            file_bytes = await file.download_as_bytearray()
            text = self.parser.clean_text(await self.parser.parse(bytes(file_bytes), filename))
            if not text or len(text) < 50:
                await status.edit_text(f"{E['err']} Extraction failed.")
                return
            await self._process_content(update, user_id, text, filename, status)
        except Exception as e:
            logger.error(f"Doc error: {e}"); await update.message.reply_text(f"{E['err']} Error processing file.")

    async def handle_photo(self, update: Update, ctx: ContextTypes.DEFAULT_TYPE):
        user_id, photo = update.effective_user.id, update.message.photo[-1]
        await update.message.reply_text(f"📸 Running OCR...")
        try:
            file = await ctx.bot.get_file(photo.file_id)
            file_bytes = await file.download_as_bytearray()
            text = self.parser.clean_text(await self.parser.parse_image(bytes(file_bytes)))
            if not text or len(text) < 30:
                await update.message.reply_text(f"{E['err']} No text found.")
                return
            await self._process_content(update, user_id, text, "image_ocr.txt")
        except Exception as e:
            await update.message.reply_text(f"{E['err']} OCR failed.")

    async def _process_content(self, update: Update, user_id: int, text: str, filename: str, status_msg=None):
        session_id = str(uuid.uuid4())
        msg = update.message or update.callback_query.message
        if not status_msg: status_msg = await msg.reply_text(f"{E['wait']} Analyzing research...")
        try:
            extraction = await self.extractor.extract(text)
            concepts, rels = extraction.get("concepts", []), extraction.get("relationships", [])
            domain, summary = extraction.get("domain", "Research"), extraction.get("summary", "")
            await status_msg.edit_text(f"{E['brain']} Building graph...")
            stored = await self.graph_svc.store_knowledge(user_id=user_id, session_id=session_id, concepts=concepts, relationships=rels, domain=domain)
            try: await self.vector_svc.store_document(user_id=user_id, session_id=session_id, text=text, filename=filename, concepts=[c["name"] for c in concepts], domain=domain, summary=summary)
            except Exception: pass
            await status_msg.delete()
            keyboard = InlineKeyboardMarkup([[InlineKeyboardButton(f"{E['graph']} Graph", callback_data="view_graph"), InlineKeyboardButton(f"{E['gap']} Gaps", callback_data="find_gaps")], [InlineKeyboardButton(f"{E['stats']} Stats", callback_data="analyze")]])
            await msg.reply_text(f"{E['ok']} *Update Success!*\nNodes: {stored['nodes']} | Edges: {stored['relationships']}", parse_mode=ParseMode.MARKDOWN, reply_markup=keyboard)
        except Exception as e:
            logger.error(f"Error: {e}"); await status_msg.edit_text(f"{E['err']} Processing failed.")

    async def handle_callback(self, update: Update, ctx: ContextTypes.DEFAULT_TYPE):
        query = update.callback_query
        await query.answer()
        user_id, data = query.from_user.id, query.data
        if data == "view_graph": await self.cmd_graph(update, ctx)
        elif data == "find_gaps": await self.cmd_gaps(update, ctx)
        elif data == "analyze": await self.cmd_analyze(update, ctx)
        elif data == "confirm_clear":
            await self.graph_svc.delete_user_graph(user_id)
            await query.message.edit_text(f"{E['ok']} Graph cleared!")
        elif data == "cancel_clear": await query.message.edit_text("Clear cancelled.")

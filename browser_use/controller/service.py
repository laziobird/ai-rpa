import asyncio
import json
import logging
from typing import Dict, Generic, Optional, Type, TypeVar

from browser_use.browser.context import BrowserContext
from langchain_core.language_models.chat_models import BaseChatModel
from langchain_core.prompts import PromptTemplate

# from lmnr.sdk.laminar import Laminar
from pydantic import BaseModel

from browser_use.agent.views import ActionModel, ActionResult
from browser_use.controller.registry.service import Registry
from browser_use.controller.views import (
	ClickElementAction,
	DoneAction,
	GoToUrlAction,
	InputTextAction,
	NoParamsAction,
	OpenTabAction,
	ScrollAction,
	SearchGoogleAction,
	SendKeysAction,
	SwitchTabAction,
)
from browser_use.utils import time_execution_sync

logger = logging.getLogger(__name__)

# 1. 创建一个日志记录器对象
logger_p = logging.getLogger('logger_p')
logger_p.setLevel(logging.DEBUG)  # 设置日志级别为DEBUG

# 2. 创建一个日志处理器，用于将日志写入文件
import os
# 获取项目根目录
ROOT_DIR = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
file_handler = logging.FileHandler(os.path.join(ROOT_DIR, 'examples/rpa/llm_context.log'))
file_handler.setLevel(logging.DEBUG)

# 3. 将处理器添加到日志记录器中
logger_p.addHandler(file_handler)

Context = TypeVar('Context')


class Controller(Generic[Context]):
	def __init__(
		self,
		exclude_actions: list[str] = [],
		output_model: Optional[Type[BaseModel]] = None,
	):
		self.registry = Registry[Context](exclude_actions)

		# 添加内部方法用于日志记录元素关键信息
		def _log_element_info(element_node, action_type: str = "Element info"):
			"""记录可被 Playwright 识别的元素关键属性信息"""
			attributes_info = {}
			
			# 收集关键属性
			for key, value in element_node.attributes.items():
				# 只保留 Playwright 常用的识别属性
				if key in ['id', 'class', 'name', 'type', 'value', 'placeholder', 'role', 'aria-label', 'data-testid', 'title']:
					attributes_info[key] = value
			
			# 构建元素选择器信息
			selectors = []
			
			# ID 选择器 (优先级最高)
			if 'id' in attributes_info:
				selectors.append(f"#id selector: #{attributes_info['id']}")
			
			# CSS 类选择器
			if 'class' in attributes_info:
				class_names = attributes_info['class'].strip().split()
				if class_names:
					selectors.append(f"CSS class selector: .{'.'.join(class_names)}")
			
			# 其他属性选择器
			for key, value in attributes_info.items():
				if key not in ['id', 'class']:
					selectors.append(f"Attribute selector: [{key}=\"{value}\"]")
			
			# XPath 选择器
			selectors.append(f"XPath: {element_node.xpath}")
			
			# 文本选择器 (如果有文本内容)
			text_content = element_node.get_all_text_till_next_clickable_element(max_depth=1)
			if text_content and len(text_content) < 100:  # 限制文本长度
				selectors.append(f"Text selector: :text(\"{text_content}\")")
			
			# 确定元素是否在视口内
			viewport_status = "in viewport" if element_node.is_in_viewport else "not in viewport"
			
			# 记录日志
			logger_p.debug(f"------------------ {action_type} ------------------")
			logger_p.debug(f"Element: <{element_node.tag_name}> ")
			logger_p.debug(f"Interactive: {element_node.is_interactive}, Top element: {element_node.is_top_element}")
			
			if attributes_info:
				logger_p.debug(f"Key attributes: {attributes_info}")
			
			logger_p.debug("Playwright selectors:")
			for i, selector in enumerate(selectors, 1):
				logger_p.debug(f"  {i}. {selector}")
				
			if element_node.viewport_coordinates:
				logger_p.debug(f"Viewport coordinates: {element_node.viewport_coordinates}")
				
			logger_p.debug("--------------------------------------------------")

		"""Register all default browser actions"""

		if output_model is not None:

			@self.registry.action('Complete task', param_model=output_model)
			async def done(params: BaseModel):
				return ActionResult(is_done=True, extracted_content=params.model_dump_json())
		else:

			@self.registry.action('Complete task', param_model=DoneAction)
			async def done(params: DoneAction):
				return ActionResult(is_done=True, extracted_content=params.text)

		# Basic Navigation Actions
		@self.registry.action(
			'Search the query in Google in the current tab, the query should be a search query like humans search in Google, concrete and not vague or super long. More the single most important items. ',
			param_model=SearchGoogleAction,
		)
		async def search_google(params: SearchGoogleAction, browser: BrowserContext):
			page = await browser.get_current_page()
			await page.goto(f'https://www.google.com/search?q={params.query}&udm=14')
			await page.wait_for_load_state()
			msg = f'🔍  Searched for "{params.query}" in Google'
			logger.info(msg)
			return ActionResult(extracted_content=msg, include_in_memory=True)

		##TODO 页面跳转 playwright goto
		@self.registry.action('Navigate to URL in the current tab', param_model=GoToUrlAction)
		async def go_to_url(params: GoToUrlAction, browser: BrowserContext):
			logger.debug("ME_go_to_url "+params.url)
			logger_p.debug(" Navigate action, navigate to URL in the current tab , and url is " + params.url)
			page = await browser.get_current_page()
			await page.goto(params.url)
			await page.wait_for_load_state()
			msg = f'🔗  Navigated to {params.url}'
			logger.info(msg)
			return ActionResult(extracted_content=msg, include_in_memory=True)

		@self.registry.action('Go back', param_model=NoParamsAction)
		async def go_back(_: NoParamsAction, browser: BrowserContext):
			await browser.go_back()
			msg = '🔙  Navigated back'
			logger.info(msg)
			logger_p.debug(" Navigated back ")
			return ActionResult(extracted_content=msg, include_in_memory=True)

		# Element Interaction Actions
		@self.registry.action('Click element', param_model=ClickElementAction)
		async def click_element(params: ClickElementAction, browser: BrowserContext):
			session = await browser.get_session()

			if params.index not in await browser.get_selector_map():
				raise Exception(f'Element with index {params.index} does not exist - retry or use alternative actions')

			element_node = await browser.get_dom_element_by_index(params.index)
			initial_pages = len(session.context.pages)

			# if element has file uploader then dont click
			if await browser.is_file_uploader(element_node):
				msg = f'Index {params.index} - has an element which opens file upload dialog. To upload files please use a specific function to upload files '
				logger.info(msg)
				return ActionResult(extracted_content=msg, include_in_memory=True)

			msg = None

			try:
				# 在点击前记录元素信息
				_log_element_info(element_node, "Click element")
				
				download_path = await browser._click_element_node(element_node)
				if download_path:
					msg = f'💾  Downloaded file to {download_path}'
				else:
					msg = f'🖱️  Clicked button with index {params.index}: {element_node.get_all_text_till_next_clickable_element(max_depth=2)}'

				logger.info(msg)
				logger.debug(f' click_element | Element xpath: {element_node.xpath}')

				if len(session.context.pages) > initial_pages:
					new_tab_msg = 'New tab opened - switching to it'
					msg += f' - {new_tab_msg}'
					logger.info(new_tab_msg)
					await browser.switch_to_tab(-1)
				return ActionResult(extracted_content=msg, include_in_memory=True)
			except Exception as e:
				logger.warning(f'Element not clickable with index {params.index} - most likely the page changed')
				return ActionResult(error=str(e))

		@self.registry.action(
			'Input text into a input interactive element',
			param_model=InputTextAction,
		)
		async def input_text(params: InputTextAction, browser: BrowserContext, has_sensitive_data: bool = False):
			if params.index not in await browser.get_selector_map():
				raise Exception(f'Element index {params.index} does not exist - retry or use alternative actions')

			element_node = await browser.get_dom_element_by_index(params.index)
			
			# 在输入前记录元素信息
			_log_element_info(element_node, "Input text")
			
			await browser._input_text_element_node(element_node, params.text)
			if not has_sensitive_data:
				msg = f'⌨️  Input {params.text} into index {params.index}'
			else:
				msg = f'⌨️  Input sensitive data into index {params.index}'
			logger.info(msg)
			logger.debug(f'input_text | Element xpath: {element_node.xpath}')
			
			return ActionResult(extracted_content=msg, include_in_memory=True)

		# Tab Management Actions
		@self.registry.action('Switch tab', param_model=SwitchTabAction)
		async def switch_tab(params: SwitchTabAction, browser: BrowserContext):
			await browser.switch_to_tab(params.page_id)
			# Wait for tab to be ready
			page = await browser.get_current_page()
			await page.wait_for_load_state()
			msg = f'🔄  Switched to tab {params.page_id}'
			logger.info(msg)
			logger_p.debug(
				" This is a switch tab, and page_id : "+{params.page_id}.__str__())
			return ActionResult(extracted_content=msg, include_in_memory=True)

		@self.registry.action('Open url in new tab', param_model=OpenTabAction)
		async def open_tab(params: OpenTabAction, browser: BrowserContext):
			await browser.create_new_tab(params.url)
			msg = f'🔗  Opened new tab with {params.url}'
			logger.info(msg)
			logger.debug(f' open_tab | : ')
			logger_p.debug(" Open url in new tab , and url is : " + params.url)
			return ActionResult(extracted_content=msg, include_in_memory=True)

		# Content Actions
		@self.registry.action(
			'Extract page content to retrieve specific information from the page, e.g. all company names, a specifc description, all information about, links with companies in structured format or simply links',
		)
		async def extract_content(goal: str, browser: BrowserContext, page_extraction_llm: BaseChatModel):
			page = await browser.get_current_page()
			import markdownify
			# 把html 转换成 md
			content = markdownify.markdownify(await page.content())

			prompt = 'Your task is to extract the content of the page. You will be given a page and a goal and you should extract all relevant information around this goal from the page. If the goal is vague, summarize the page. Respond in json format. Extraction goal: {goal}, Page: {page}'
			template = PromptTemplate(input_variables=['goal', 'page'], template=prompt)
			try:
				output = page_extraction_llm.invoke(template.format(goal=goal, page=content))
				msg = f'📄  Extracted from page\n: {output.content}\n'
				logger.info(msg)
				return ActionResult(extracted_content=msg, include_in_memory=True)
			except Exception as e:
				logger.debug(f'Error extracting content: {e}')
				msg = f'📄  Extracted from page\n: {content}\n'
				logger.info(msg)
				return ActionResult(extracted_content=msg)

		@self.registry.action(
			'Scroll down the page by pixel amount - if no amount is specified, scroll down one page',
			param_model=ScrollAction,
		)
		async def scroll_down(params: ScrollAction, browser: BrowserContext):
			page = await browser.get_current_page()
			if params.amount is not None:
				await page.evaluate(f'window.scrollBy(0, {params.amount});')
			else:
				await page.evaluate('window.scrollBy(0, window.innerHeight);')

			amount = f'{params.amount} pixels' if params.amount is not None else 'one page'
			msg = f'🔍  Scrolled down the page by {amount}'
			logger_p.debug(
				" Scrolled down the page by " + amount)
			logger.info(msg)
			return ActionResult(
				extracted_content=msg,
				include_in_memory=True,
			)

		# scroll up
		@self.registry.action(
			'Scroll up the page by pixel amount - if no amount is specified, scroll up one page',
			param_model=ScrollAction,
		)
		async def scroll_up(params: ScrollAction, browser: BrowserContext):
			page = await browser.get_current_page()
			if params.amount is not None:
				await page.evaluate(f'window.scrollBy(0, -{params.amount});')
			else:
				await page.evaluate('window.scrollBy(0, -window.innerHeight);')

			amount = f'{params.amount} pixels' if params.amount is not None else 'one page'
			msg = f'🔍  Scrolled up the page by {amount}'
			logger_p.debug(
				" Scrolled up the page by " + amount)
			logger.info(msg)
			return ActionResult(
				extracted_content=msg,
				include_in_memory=True,
			)

		# send keys
		@self.registry.action(
			'Send strings of special keys like Escape,Backspace, Insert, PageDown, Delete, Enter, Shortcuts such as `Control+o`, `Control+Shift+T` are supported as well. This gets used in keyboard.press. ',
			param_model=SendKeysAction,
		)
		async def send_keys(params: SendKeysAction, browser: BrowserContext):
			page = await browser.get_current_page()

			try:
				await page.keyboard.press(params.keys)
			except Exception as e:
				if 'Unknown key' in str(e):
					# loop over the keys and try to send each one
					for key in params.keys:
						try:
							await page.keyboard.press(key)
						except Exception as e:
							logger.debug(f'Error sending key {key}: {str(e)}')
							raise e
				else:
					raise e
			msg = f'⌨️  Sent keys: {params.keys}'
			logger_p.debug("Send keys Action , first call browser.get_current_page(), then call page.keyboard.press "
						   "  These keys are " +  {params.keys}.__str__())
						   #+ " . And the page : " + browser.get_current_page().__str__()
						   #+ " . Then start to load new page " )
			logger.info(msg)
			return ActionResult(extracted_content=msg, include_in_memory=True)

		@self.registry.action(
			description='If you dont find something which you want to interact with, scroll to it',
		)
		async def scroll_to_text(text: str, browser: BrowserContext):  # type: ignore
			page = await browser.get_current_page()
			try:
				##TODO locator click
				logger_p.debug(
					" Scroll to text , and the resource code is  "
					"""
					locators = [
					page.get_by_text(text, exact=False),
					page.locator(f'text={text}'),
					page.locator(f"//*[contains(text(), '{text}')]"),
					]
					"""
				),
				# Try different locator strategies
				locators = [
					page.get_by_text(text, exact=False),
					page.locator(f'text={text}'),
					page.locator(f"//*[contains(text(), '{text}')]"),
				]

				for locator in locators:
					try:
						# First check if element exists and is visible
						if await locator.count() > 0 and await locator.first.is_visible():
							await locator.first.scroll_into_view_if_needed()
							await asyncio.sleep(0.5)  # Wait for scroll to complete
							msg = f'🔍  Scrolled to text: {text}'
							logger.info(msg)
							return ActionResult(extracted_content=msg, include_in_memory=True)
					except Exception as e:
						logger.debug(f'Locator attempt failed: {str(e)}')
						continue

				msg = f"Text '{text}' not found or not visible on page"
				logger.info(msg)
				return ActionResult(extracted_content=msg, include_in_memory=True)

			except Exception as e:
				msg = f"Failed to scroll to text '{text}': {str(e)}"
				logger.error(msg)
				return ActionResult(error=msg, include_in_memory=True)

		@self.registry.action(
			description='Get all options from a native dropdown',
		)
		async def get_dropdown_options(index: int, browser: BrowserContext) -> ActionResult:
			"""Get all options from a native dropdown"""
			page = await browser.get_current_page()
			selector_map = await browser.get_selector_map()
			dom_element = selector_map[index]

			try:
				# Frame-aware approach since we know it works
				all_options = []
				frame_index = 0

				for frame in page.frames:
					try:
						options = await frame.evaluate(
							"""
							(xpath) => {
								const select = document.evaluate(xpath, document, null,
									XPathResult.FIRST_ORDERED_NODE_TYPE, null).singleNodeValue;
								if (!select) return null;

								return {
									options: Array.from(select.options).map(opt => ({
										text: opt.text, //do not trim, because we are doing exact match in select_dropdown_option
										value: opt.value,
										index: opt.index
									})),
									id: select.id,
									name: select.name
								};
							}
						""",
							dom_element.xpath,
						)

						if options:
							logger.debug(f'Found dropdown in frame {frame_index}')
							logger.debug(f'Dropdown ID: {options["id"]}, Name: {options["name"]}')

							formatted_options = []
							for opt in options['options']:
								# encoding ensures AI uses the exact string in select_dropdown_option
								encoded_text = json.dumps(opt['text'])
								formatted_options.append(f'{opt["index"]}: text={encoded_text}')

							all_options.extend(formatted_options)

					except Exception as frame_e:
						logger.debug(f'Frame {frame_index} evaluation failed: {str(frame_e)}')

					frame_index += 1

				if all_options:
					msg = '\n'.join(all_options)
					msg += '\nUse the exact text string in select_dropdown_option'
					logger.info(msg)
					return ActionResult(extracted_content=msg, include_in_memory=True)
				else:
					msg = 'No options found in any frame for dropdown'
					logger.info(msg)
					return ActionResult(extracted_content=msg, include_in_memory=True)

			except Exception as e:
				logger.error(f'Failed to get dropdown options: {str(e)}')
				msg = f'Error getting options: {str(e)}'
				logger.info(msg)
				return ActionResult(extracted_content=msg, include_in_memory=True)

		@self.registry.action(
			description='Select dropdown option for interactive element index by the text of the option you want to select',
		)
		async def select_dropdown_option(
			index: int,
			text: str,
			browser: BrowserContext,
		) -> ActionResult:
			"""Select dropdown option by the text of the option you want to select"""
			page = await browser.get_current_page()
			selector_map = await browser.get_selector_map()
			dom_element = selector_map[index]

			# Validate that we're working with a select element
			if dom_element.tag_name != 'select':
				logger.error(f'Element is not a select! Tag: {dom_element.tag_name}, Attributes: {dom_element.attributes}')
				msg = f'Cannot select option: Element with index {index} is a {dom_element.tag_name}, not a select'
				return ActionResult(extracted_content=msg, include_in_memory=True)

			logger.debug(f"Attempting to select '{text}' using xpath: {dom_element.xpath}")
			logger.debug(f'Element attributes: {dom_element.attributes}')
			logger.debug(f'Element tag: {dom_element.tag_name}')
			logger_p.debug(f"Attempting to select '{text}' using xpath: {dom_element.xpath}, Attributes: {dom_element.attributes}'")
			xpath = '//' + dom_element.xpath

			try:
				frame_index = 0
				for frame in page.frames:
					try:
						logger.debug(f'Trying frame {frame_index} URL: {frame.url}')

						# First verify we can find the dropdown in this frame
						find_dropdown_js = """
							(xpath) => {
								try {
									const select = document.evaluate(xpath, document, null,
										XPathResult.FIRST_ORDERED_NODE_TYPE, null).singleNodeValue;
									if (!select) return null;
									if (select.tagName.toLowerCase() !== 'select') {
										return {
											error: `Found element but it's a ${select.tagName}, not a SELECT`,
											found: false
										};
									}
									return {
										id: select.id,
										name: select.name,
										found: true,
										tagName: select.tagName,
										optionCount: select.options.length,
										currentValue: select.value,
										availableOptions: Array.from(select.options).map(o => o.text.trim())
									};
								} catch (e) {
									return {error: e.toString(), found: false};
								}
							}
						"""

						dropdown_info = await frame.evaluate(find_dropdown_js, dom_element.xpath)

						if dropdown_info:
							if not dropdown_info.get('found'):
								logger.error(f'Frame {frame_index} error: {dropdown_info.get("error")}')
								continue

							logger.debug(f'Found dropdown in frame {frame_index}: {dropdown_info}')

							# "label" because we are selecting by text
							# nth(0) to disable error thrown by strict mode
							# timeout=1000 because we are already waiting for all network events, therefore ideally we don't need to wait a lot here (default 30s)
							selected_option_values = (
								await frame.locator('//' + dom_element.xpath).nth(0).select_option(label=text, timeout=1000)
							)

							msg = f'selected option {text} with value {selected_option_values}'
							logger.info(msg + f' in frame {frame_index}')
							logger_p.debug(msg + f' in frame {frame_index}')
							return ActionResult(extracted_content=msg, include_in_memory=True)

					except Exception as frame_e:
						logger.error(f'Frame {frame_index} attempt failed: {str(frame_e)}')
						logger.error(f'Frame type: {type(frame)}')
						logger.error(f'Frame URL: {frame.url}')

					frame_index += 1

				msg = f"Could not select option '{text}' in any frame"
				logger.info(msg)
				return ActionResult(extracted_content=msg, include_in_memory=True)

			except Exception as e:
				msg = f'Selection failed: {str(e)}'
				logger.error(msg)
				return ActionResult(error=msg, include_in_memory=True)

	# Register ---------------------------------------------------------------

	def action(self, description: str, **kwargs):
		"""Decorator for registering custom actions

		@param description: Describe the LLM what the function does (better description == better function calling)
		"""
		return self.registry.action(description, **kwargs)

	# Act --------------------------------------------------------------------

	@time_execution_sync('--act')
	async def act(
		self,
		action: ActionModel,
		browser_context: BrowserContext,
		#
		page_extraction_llm: Optional[BaseChatModel] = None,
		sensitive_data: Optional[Dict[str, str]] = None,
		available_file_paths: Optional[list[str]] = None,
		#
		context: Context | None = None,
	) -> ActionResult:
		"""Execute an action"""
		## TODO 执行真正的Action
		try:
			for action_name, params in action.model_dump(exclude_unset=True).items():
				if params is not None:
					# with Laminar.start_as_current_span(
					# 	name=action_name,
					# 	input={
					# 		'action': action_name,
					# 		'params': params,
					# 	},
					# 	span_type='TOOL',
					# ):
					logger.info(f'Executing action: {action_name}({params})')
					result = await self.registry.execute_action(
						action_name,
						params,
						browser=browser_context,
						page_extraction_llm=page_extraction_llm,
						sensitive_data=sensitive_data,
						available_file_paths=available_file_paths,
						context=context,
					)

					# Laminar.set_span_output(result)

					if isinstance(result, str):
						return ActionResult(extracted_content=result)
					elif isinstance(result, ActionResult):
						return result
					elif result is None:
						return ActionResult()
					else:
						raise ValueError(f'Invalid action result type: {type(result)} of {result}')
			return ActionResult()
		except Exception as e:
			raise e

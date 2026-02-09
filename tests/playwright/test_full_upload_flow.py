"""COMPREHENSIVE Playwright test for COMPLETE upload flow with LONG timeouts."""
import asyncio
import subprocess
import time
import signal
from pathlib import Path
from playwright.async_api import async_playwright

server_process = None

def start_server():
    global server_process
    print("🚀 Starting server...")
    server_process = subprocess.Popen(
        ["uv", "run", "agent-catalogue", "serve", "--host", "127.0.0.1", "--port", "8000"],
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        cwd="/home/dicolomb/amplifier-app-agent-catalogue"
    )
    time.sleep(10)  # Give server time to fully start
    print(f"   Server PID: {server_process.pid}")

def stop_server():
    global server_process
    if server_process:
        print("\n🛑 Stopping server...")
        server_process.send_signal(signal.SIGTERM)
        try:
            server_process.wait(timeout=3)
        except:
            server_process.kill()

async def test_upload_flow():
    """Test COMPLETE upload flow with LONG timeouts for LLM processing."""
    
    test_file = Path("/home/dicolomb/amplifier-app-agent-catalogue/test_agents/csv-dsl-development-assistant.md")
    if not test_file.exists():
        print(f"❌ Test file not found: {test_file}")
        return False
    
    async with async_playwright() as p:
        print("\n🌐 Launching browser...")
        browser = await p.chromium.launch(headless=False)  # Visible for debugging
        context = await browser.new_context()
        page = await context.new_page()
        
        # Capture ALL console messages with details
        console_logs = []
        def log_console(msg):
            log_entry = f"[{msg.type}] {msg.text}"
            console_logs.append(log_entry)
            # Print errors immediately
            if msg.type == "error":
                print(f"   ⚠️ Console: {log_entry}")
        
        page.on("console", log_console)
        
        # Capture page errors
        page_errors = []
        def log_error(error):
            err_msg = str(error)
            page_errors.append(err_msg)
            print(f"   ❌ Page Error: {err_msg}")
        
        page.on("pageerror", log_error)
        
        try:
            # Step 1: Load upload page
            print("\n📄 Step 1: Loading upload page...")
            await page.goto("http://127.0.0.1:8000/upload", wait_until="domcontentloaded", timeout=30000)
            await page.wait_for_timeout(2000)
            
            if page_errors:
                print(f"   ❌ Page has JavaScript errors, aborting")
                return False
            
            print("   ✅ Page loaded")
            
            # Step 2: Upload file
            print("\n📤 Step 2: Uploading test file...")
            file_input = page.locator('input[type="file"]')
            await file_input.set_input_files(str(test_file))
            await page.wait_for_timeout(1000)
            
            # Verify file name displayed
            file_name_el = page.locator('#file-name')
            if await file_name_el.is_visible():
                print(f"   ✅ File uploaded: {await file_name_el.text_content()}")
            else:
                print("   ❌ File name not displayed")
                return False
            
            # Step 3: Click Analyze button
            print("\n🔍 Step 3: Starting analysis (LONG timeout for LLM processing)...")
            analyze_btn = page.locator('#analyze-btn')
            await analyze_btn.click()
            
            # Wait for analysis with VERY LONG timeout (5 minutes for LLM calls)
            print("   ⏳ Waiting for analysis to complete (up to 5 minutes)...")
            
            try:
                # Wait for either success or error
                await page.wait_for_selector(
                    '#step-2-content:not(.hidden), #analyze-error',
                    timeout=300000  # 5 MINUTES
                )
                
                # Check if we got results or error
                error_el = page.locator('#analyze-error')
                if await error_el.is_visible():
                    error_text = await error_el.text_content()
                    print(f"   ❌ Analysis failed: {error_text}")
                    return False
                
                # Check for results
                step2_content = page.locator('#step-2-content')
                if await step2_content.is_visible():
                    print("   ✅ Analysis completed")
                    
                    # Check if metadata displayed
                    metadata = page.locator('#metadata-display')
                    if await metadata.is_visible():
                        metadata_text = await metadata.text_content()
                        print(f"   📊 Metadata: {metadata_text[:200]}...")
                    else:
                        print("   ⚠️ No metadata displayed")
                        return False
                else:
                    print("   ❌ Step 2 content not visible")
                    return False
                
            except Exception as e:
                print(f"   ❌ Analysis timeout or error: {e}")
                
                # Capture activity feed for debugging
                activity_feed = page.locator('#analyze-activity-feed')
                if await activity_feed.is_visible():
                    feed_text = await activity_feed.text_content()
                    print(f"\n📋 Activity Feed captured:")
                    print(feed_text)
                
                return False
            
            print("\n✅ UPLOAD FLOW TEST PASSED")
            return True
            
        except Exception as e:
            print(f"\n❌ Test failed with exception: {e}")
            return False
        
        finally:
            # Print all console logs for debugging
            if console_logs:
                print(f"\n📝 Console Logs ({len(console_logs)} total):")
                for log in console_logs[-20:]:  # Last 20
                    print(f"   {log}")
            
            await browser.close()

if __name__ == "__main__":
    try:
        start_server()
        passed = asyncio.run(test_upload_flow())
        
        print("\n" + "="*70)
        if passed:
            print("🎉 UPLOAD FLOW TEST PASSED")
        else:
            print("❌ UPLOAD FLOW TEST FAILED - See details above")
        print("="*70)
        
        exit(0 if passed else 1)
    finally:
        stop_server()

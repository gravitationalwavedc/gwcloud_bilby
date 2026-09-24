"""Causal meta-tests proving accessibility detectors fail on seeded defects."""

from .accessibility_assertions import (
    assert_active_element,
    assert_no_active_animation,
    assert_no_contrast_failures,
    assert_no_horizontal_overflow,
    assert_no_serious_axe_violations,
    assert_target_sizes,
)
from .utils import AsyncE2ETestCase, async_e2e_test, load_axe


class AccessibilityDetectorMetaTests(AsyncE2ETestCase):
    """Prove six gates pass clean controls and reject one causal defect each."""

    async def asetUp(self):
        self.page = await self.browser_context.new_page()

    async def aTearDown(self):
        if self.page is not None:
            await self.page.close()
            self.page = None

    @async_e2e_test
    async def test_seeded_violations_are_causally_detected(self):
        cases = (
            {
                "name": "axe serious violation",
                "clean": """
                    <!doctype html>
                    <html lang="en"><head><title>Clean axe fixture</title></head>
                    <body><main><h1>Fixture</h1>
                    <button id="subject">Continue</button></main></body></html>
                """,
                "assertion": lambda: assert_no_serious_axe_violations(self.page, "body"),
                "seed": """
                    const image = document.createElement('img');
                    image.src =
                        'data:image/gif;base64,R0lGODlhAQABAIAAAAAAAP///'
                        + 'ywAAAAAAQABAAACAUwAOw==';
                    document.querySelector('main').appendChild(image);
                """,
                "expected": "serious axe violation",
                "axe": True,
            },
            {
                "name": "horizontal overflow",
                "clean": """
                    <!doctype html>
                    <html lang="en"><head><title>Clean overflow fixture</title>
                    <style>html,body{margin:0}main{max-width:100%}</style></head>
                    <body><main>Fixture</main></body></html>
                """,
                "assertion": lambda: assert_no_horizontal_overflow(self.page),
                "seed": """
                    const defect = document.createElement('div');
                    defect.id = 'overflow-defect';
                    defect.style.cssText = 'width:200vw;height:1px';
                    document.body.appendChild(defect);
                """,
                "expected": "horizontal overflow detected",
            },
            {
                "name": "low contrast",
                "clean": """
                    <!doctype html>
                    <html lang="en"><head><title>Clean contrast fixture</title>
                    <style>#subject{color:rgb(0,0,0);background:rgb(255,255,255)}
                    </style></head><body>
                    <p id="subject">Readable text</p></body></html>
                """,
                "assertion": lambda: assert_no_contrast_failures(self.page, "#subject"),
                "seed": """
                    const subject = document.querySelector('#subject');
                    subject.style.color = 'rgb(119,119,119)';
                    subject.style.backgroundColor = 'rgb(136,136,136)';
                """,
                "expected": "computed contrast failures",
            },
            {
                "name": "target below 24px",
                "clean": """
                    <!doctype html>
                    <html lang="en"><head><title>Clean target fixture</title>
                    <style>#subject{box-sizing:border-box;width:30px;height:30px;
                    padding:0}</style></head><body>
                    <button id="subject" aria-label="Action"></button>
                    </body></html>
                """,
                "assertion": lambda: assert_target_sizes(self.page, scope_selector="body", selector="#subject"),
                "seed": """
                    document.querySelector('#subject').style.width = '20px';
                """,
                "expected": "undersized interactive targets",
            },
            {
                "name": "post-swap focus loss",
                "clean": """
                    <!doctype html>
                    <html lang="en"><head><title>Clean focus fixture</title></head>
                    <body><button id="subject" autofocus>Swap</button>
                    <div id="result"></div>
                    <script>document.querySelector('#subject').focus()</script>
                    </body></html>
                """,
                "assertion": lambda: assert_active_element(self.page, "subject"),
                "seed": """
                    document.querySelector('#result').innerHTML =
                        '<p>Swapped content</p>';
                    document.activeElement.blur();
                """,
                "expected": "post-swap focus restoration failed",
            },
            {
                "name": "reduced-motion infinite animation",
                "clean": """
                    <!doctype html>
                    <html lang="en"><head><title>Clean motion fixture</title>
                    <style>
                    #subject{animation:none}
                    @keyframes spin{to{transform:rotate(360deg)}}
                    </style></head><body>
                    <div id="subject">Loading</div></body></html>
                """,
                "assertion": lambda: assert_no_active_animation(self.page, "#subject"),
                "seed": """
                    document.querySelector('#subject').style.animation =
                        'spin 1s linear infinite';
                """,
                "expected": "active animations remain in reduced-motion mode",
                "reduced_motion": True,
            },
            {
                "name": "reduced-motion finite animation",
                "clean": """
                    <!doctype html>
                    <html lang="en"><head><title>Clean motion fixture</title>
                    <style>
                    #subject{animation:none}
                    @keyframes spin{to{transform:rotate(360deg)}}
                    </style></head><body>
                    <div id="subject">Loading</div></body></html>
                """,
                "assertion": lambda: assert_no_active_animation(self.page, "#subject"),
                "seed": """
                    document.querySelector('#subject').style.animation =
                        'spin 1s linear 2';
                """,
                "expected": "active animations remain in reduced-motion mode",
                "reduced_motion": True,
            },
        )

        for case in cases:
            with self.subTest(gate=case["name"]):
                if case.get("reduced_motion"):
                    await self.page.emulate_media(reduced_motion="reduce")
                await self.page.set_content(case["clean"])
                if case.get("axe"):
                    await load_axe(self.page)
                await case["assertion"]()

                await self.page.evaluate(case["seed"])
                with self.assertRaises(AssertionError) as caught:
                    await case["assertion"]()
                self.assertIn(case["expected"], str(caught.exception))

                await self.page.set_content(case["clean"])
                if case.get("axe"):
                    await load_axe(self.page)
                await case["assertion"]()

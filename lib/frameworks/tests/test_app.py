from django.test import SimpleTestCase


class Example(SimpleTestCase):
    def test_application(self):
        self.assertEqual(2 + 2, 4)

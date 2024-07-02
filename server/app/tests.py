"""
This file demonstrates writing tests using the unittest module. These will pass
when you run "manage.py test".
"""

from django.test import TestCase

class ViewTest(TestCase):
    """Tests for the application views."""

    def setUp(self):
        """Set up any state specific to the execution of the test case."""
        pass  # Add any setup code here if needed

    def test_home_page_contains_expected_content(self):
        """Tests the home page contains 'Home Page'."""
        response = self.client.get('/')
        self.assertContains(response, 'Home Page', status_code=200)

    def test_contact_page_contains_expected_content(self):
        """Tests the contact page contains 'Contact'."""
        response = self.client.get('/contact')
        self.assertContains(response, 'Contact', count=3, status_code=200)

    def test_about_page_contains_expected_content(self):
        """Tests the about page contains 'About'."""
        response = self.client.get('/about')
        self.assertContains(response, 'About', count=3, status_code=200)

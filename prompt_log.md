# Prompt Log

These are representative prompts from the process of building and refining this
project.

1. I’m building a small Python tool to download SEC 10-K filings and convert
   them to PDFs. Add the basic project files, including dependencies, a
   `.gitignore`, an environment-variable example, and a README with setup steps
   for Windows, macOS, and Linux.

2. Create an SEC client that uses my SEC User-Agent, looks up company
   identifiers, and finds the latest 10-K filing with its metadata. Include clear errors and useful logging.

3. Add a converter and a simple runner that processes a configurable list of
   companies one at a time and saves a separate output file for each company.

4. The PDF converter is struggling with SEC filing HTML. Replace it with
   Playwright and Chromium, and make sure temporary files are cleaned up.

5. Images from the filing are missing in the PDF. Investigate how the HTML's
   relative image paths can be handled reliably.

6. Fix the image paths without changing the filing's UTF-8 encoding. Keep the
   change simple and preserve the original HTML content as much as possible.

7. Review the project as a standalone tool. Remove code and dependencies that
   are genuinely unused, and keep the README consistent with how the project
   works.

8. Make the company list configurable through an environment variable, so I can
   change which companies are processed without editing Python code.

9. Make the terminal output easier to read, with clear progress for each
   company and a useful summary when processing finishes.

10. Add a subtle separator between company progress messages. Keep emojis
    minimal and use them only for success, failure, and the final result.

11. Add a small set of offline unit tests for company configuration, selecting
    the latest 10-K, and continuing when one company fails.

12. Update the README to explain the project structure, the purpose of each
    module, and how paths for configuration, temporary files, and generated
    PDFs are handled.

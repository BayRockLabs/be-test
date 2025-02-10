import cProfile
import pstats
import io
from c2c_modules.models import ProfilingResult
from django.utils import timezone

class CProfileMiddleware:
    """
    Middleware that profiles view execution times using cProfile and stores the results in the database.

    This middleware is only active if both `DEBUG` is set to True and the `PROFILE` setting is set to 'DEMO'.
    It profiles the request handling process and stores the functions that exceed a specified threshold of
    cumulative time (default is 2 seconds) in the `ProfilingResult` model.

    The profiling data includes:
    - The path of the request
    - The function name (including module and line number)
    - The cumulative execution time in seconds
    - The timestamp when the profiling occurred

    The profiling results are saved into the `ProfilingResult` model for later inspection.

    Attributes:
        get_response (callable): The next middleware or view in the Django request/response cycle.

    Methods:
        __call__(request):
            Profiles the request if `DEBUG` is True and `PROFILE` is 'DEMO'.
            Saves the profiling data to the database for functions that exceed the threshold time.
    """
    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        # Check if DEBUG is True and PROFILE is set to 'DEMO'
        # if not DEBUG or PROFILE != 'DEMO':
        #     return self.get_response(request)

        # Start profiling
        profiler = cProfile.Profile()
        profiler.enable()

        # Process the request
        response = self.get_response(request)

        # Stop profiling
        profiler.disable()
        s = io.StringIO()
        ps = pstats.Stats(profiler, stream=s).sort_stats('cumulative')

        # Set a threshold for cumulative time
        threshold = 2  # seconds
        ps.print_stats()

        time_consuming_stats = []
        for func, stat in ps.stats.items():
            cumulative_time = stat[2]
            if cumulative_time > threshold:
                func_name = f"{func[0]}:{func[2]}"
                time_consuming_stats.append((func_name, cumulative_time))

        # Save the profiling results to the database
        for func_name, cumulative_time in time_consuming_stats:
            ProfilingResult.objects.create(
                path=request.path,
                function_name=func_name,
                cumulative_time=cumulative_time,
                timestamp=timezone.now()
            )

        return response

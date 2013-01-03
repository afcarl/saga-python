# -*- coding: utf-8 -*-
# vim: tabstop=8 expandtab shiftwidth=4 softtabstop=4

__author__    = "Andre Merzky"
__copyright__ = "Copyright 2012, The SAGA Project"
__license__   = "MIT"

""" SAGA job interface
"""


import saga.exceptions
import saga.task

from   saga.attributes    import Attributes
from   saga.base          import Base
from   saga.async         import Async
from   saga.job.constants import *



# class Job (Object, Async, Attributes, Permissions) :
class Job (Base, Attributes, Async) :
    
    def __init__ (self, _method_type='run', 
                  _adaptor=None, _adaptor_state={}, _ttype=None) : 
        '''
        url:       saga.Url
        flags:     flags enum
        session:   saga.Session
        ret:       obj

        _adaptor`` references the adaptor class instance which created this task
        instance.

        The ``_method_type`` parameter is flattened into the job constructor to
        satisfy the bulk optimization properties of the saga.Task class, whose
        interface is implemented by saga.job.Job.
        ``_method_type`` specifies the SAGA API method which task is
        representing.  For jobs, that is the 'run' method.

        We don't have a create classmethod -- jobs are never constructed by the user
        '''

        if not _adaptor :
            raise saga.exceptions.IncorrectState ("saga.job.Job constructor is private")


        # we need to keep _method_type around, for the task interface (see
        # :class:`saga.Task`)
        self._method_type = _method_type

        # We need to specify a schema for adaptor selection -- and
        # simply choose the first one the adaptor offers.
        scheme = _adaptor.get_schemas()[0]

        Base.__init__ (self, scheme, _adaptor, _adaptor_state, ttype=None)


        # set attribute interface properties
        self._attributes_allow_private (True)
        self._attributes_extensible    (False)
        self._attributes_camelcasing   (True)

        # register properties with the attribute interface 
        self._attributes_register   (STATE,            saga.job.UNKNOWN, self.ENUM,   self.SCALAR, self.READONLY)
        self._attributes_register   (EXIT_CODE,        None,             self.INT,    self.SCALAR, self.READONLY)
        self._attributes_register   (CREATED,          None,             self.INT,    self.SCALAR, self.READONLY)
        self._attributes_register   (STARTED,          None,             self.INT,    self.SCALAR, self.READONLY)
        self._attributes_register   (FINISHED,         None,             self.INT,    self.SCALAR, self.READONLY)
        self._attributes_register   (EXECUTION_HOSTS,  None,             self.STRING, self.VECTOR, self.READONLY)
        self._attributes_register   (ID,               None,             self.STRING, self.SCALAR, self.READONLY)
        self._attributes_register   (SERVICE_URL,      None,             self.URL,    self.SCALAR, self.READONLY)

        self._attributes_set_enums  (STATE,   [saga.job.UNKNOWN, 
                                               saga.job.NEW, saga.job.RUNNING,
                                               saga.job.DONE,
                                               saga.job.FAILED,  
                                               saga.job.CANCELED, 
                                               saga.job.SUSPENDED])

        self._attributes_set_getter (STATE,           self.get_state)
        self._attributes_set_getter (ID,              self.get_id)
        self._attributes_set_getter (EXIT_CODE,       self._get_exit_code)
        self._attributes_set_getter (CREATED,         self._get_created)
        self._attributes_set_getter (STARTED,         self._get_started)
        self._attributes_set_getter (FINISHED,        self._get_finished)
        self._attributes_set_getter (EXECUTION_HOSTS, self._get_execution_hosts)

 


    def get_id (self, ttype=None) :
        '''
        ttype:     saga.task.type enum
        ret:       String / saga.Task  
        '''
        return self._adaptor.get_id (ttype=ttype)


    def get_description (self, ttype=None) :
        '''
        ttype:     saga.task.type enum
        ret:       saga.job.Description / saga.Task  
        '''
        return self._adaptor.get_description (ttype=ttype)


    def get_stdin (self, ttype=None) :
        '''
        ttype:     saga.task.type enum
        ret:       os.File / saga.Task
        '''
        return self._adaptor.get_stdin (ttype=ttype)


    def get_stdout (self, ttype=None) :
        '''
        ttype:     saga.task.type enum
        ret:       os.File / saga.Task
        '''
        return self._adaptor.get_stdout (ttype=ttype)


    def get_stderr (self, ttype=None) :
        '''
        ttype:     saga.task.type enum
        ret:       os.File / saga.Task
        '''
        return self._adaptor.get_stderr (ttype=ttype)


    def suspend (self, ttype=None) :
        '''
        ttype:     saga.task.type enum
        ret:       None / saga.Task
        '''
        return self._adaptor.suspend (ttype=ttype)


    def resume (self, ttype=None) :
        '''
        ttype:     saga.task.type enum
        ret:       None / saga.Task
        '''
        return self._adaptor.resume (ttype=ttype)


    def checkpoint (self, ttype=None) :
        '''
        ttype:     saga.task.type enum
        ret:       None / saga.Task
        '''
        return self._adaptor.checkpoint (ttype=ttype)


    def migrate (self, jd, ttype=None) :
        '''
        jd:        saga.job.Description  
        ttype:     saga.task.type enum
        ret:       None / saga.Task
        '''
        return self._adaptor.migrate (jd, ttype=ttype)


    def signal (self, signum, ttype=None) :
        '''
        signum:    int
        ttype:     saga.task.type enum
        ret:       None / saga.Task
        '''
        return self._adaptor.signal (signum, ttype=ttype)


    description = property (get_description)  # Description
    stdin       = property (get_stdin)        # os.File
    stdout      = property (get_stdout)       # os.File
    stderr      = property (get_stderr)       # os.File


    #-----------------------------------------------------------------
    #
    # task methods flattened into job :-/
    #
    def run (self, ttype=None) :
        '''
        ret:        None
        '''
        return self._adaptor.run (ttype=ttype)


    def cancel (self, timeout=None, ttype=None) :
        '''
        timeout:    float
        ret:        None
        '''
        return self._adaptor.cancel (timeout, ttype=ttype)


    def wait (self, timeout=-1, ttype=None) :
        '''
        timeout:    float 
        ret:        None
        '''
        return self._adaptor.wait (timeout, ttype=ttype)


    def get_state (self, ttype=None) :
        '''
        ret:        Task/Job state enum
        '''
        return self._adaptor.get_state (ttype=ttype)


    def get_result (self, ttype=None) :
        '''
        ret:        <result type>
        note:       this will always return None for a job.
        '''
        return self._adaptor.get_result (ttype=ttype)


    def get_object (self, ttype=None) :
        """ :todo: describe me
            :note: this will return the job_service which created the job.
        """
        return self._adaptor.get_object (ttype=ttype)


    def re_raise (self, ttype=None) :
        """ :todo: describe me

            :note: if job failed, that will re-raise an exception describing 
                   why, if that exists.  Otherwise, the call does nothing.

        """
        return self._adaptor.re_raise (ttype=ttype)


    # ----------------------------------------------------------------
    # attribute getters
    def _get_exit_code (self, ttype=None) :
        return self._adaptor.get_exit_code (ttype=ttype)

    def _get_created (self, ttype=None) :
        return self._adaptor.get_created (ttype=ttype)

    def _get_started (self, ttype=None) :
        return self._adaptor.get_started (ttype=ttype)

    def _get_finished (self, ttype=None) :
        return self._adaptor.get_finished (ttype=ttype)

    def _get_execution_hosts (self, ttype=None) :
        return self._adaptor.get_execution_hosts (ttype=ttype)

    state     = property (get_state)       # state enum
    result    = property (get_result)      # result type    (None)
    object    = property (get_object)      # object type    (job_service)
    exception = property (re_raise)        # exception type



# class Self (Job, monitoring.Steerable) :
class Self (Job) :

    def __init__(self, session=None):
    
        # # set attribute interface properties
        # self._attributes_extensible  (False)
        # self._attributes_camelcasing (True)

        self._logger  = getLogger ('saga.job.Job')
        self._logger.debug ("saga.job.Self.__init__ (%s, %s)"  \
                         % (str(session)))

        self._engine  = saga.engine.engine.getEngine ()
        self._adaptor = self._engine.bind_adaptor (self, 'saga.job.Self', 'fork', \
                                                  NOTASK, saga.engine.ANY_ADAPTOR, session)


    @classmethod
    def create (self, session=None, ttype=None) :
        '''
        session:   saga.Session
        ttype:     saga.task.type enum
        ret:       saga.Task
        '''
    
        logger = getLogger ('saga.job.Job')
        logger.debug ("saga.job.Self.create (%s, %s)"  \
                   % (str(session), str(ttype)))
    
        engine = saga.engine.engine.getEngine ()
    
        # attempt to find a suitable adaptor, which will call 
        # init_instance_async(), which returns a task as expected.
        return engine.bind_adaptor (self, 'saga.job.Self', 'fork', ttype, saga.engine.ANY_ADAPTOR, session)



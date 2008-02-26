#include <stdlib.h>
#include <stdio.h>
#include <basic_queue_driver.h>


typedef basic_queue_job_type * (submit_job_ftype)  (const basic_queue_driver_type *);
typedef void                   (clean_job_ftype)   (basic_queue_driver_type * , basic_queue_job_type * );
typedef void                   (abort_job_ftype)   (basic_queue_driver_type * , basic_queue_job_type * );
typedef ecl_job_status_type    (get_status_ftype)  (basic_queue_driver_type * , basic_queue_job_type * );
				  

struct basic_queue_job_struct {
  int __id;
};


struct basic_queue_driver_struct {
  int __id;
  submit_job_ftype * submit;
  clean_job_ftype  * clean;
  abort_job_ftype  * abort_f;
  get_status_ftype * get_status;
};

/*****************************************************************/

#define BASIC_QUEUE_ID  1000
#define BASIC_JOB_ID    2000

void basic_queue_driver_assert_cast(const basic_queue_driver_type * queue_driver) {
  if (queue_driver->__id != BASIC_QUEUE_ID) {
    fprintf(stderr,"%s: internal error - cast failed \n",__func__);
    abort();
  }
}

void basic_queue_driver_init(basic_queue_driver_type * queue_driver) {
  queue_driver->__id = BASIC_QUEUE_ID;
}

void basic_queue_job_assert_cast(const basic_queue_job_type * queue_job) {
  if (queue_job->__id != BASIC_QUEUE_ID) {
    fprintf(stderr,"%s: internal error - cast failed \n",__func__);
    abort();
  }
}

void basic_queue_job_init(basic_queue_job_type * queue_job) {
  queue_job->__id = BASIC_QUEUE_ID;
}

#undef BASIC_QUEUE_ID  
#undef BASIC_JOB_ID    

/*****************************************************************/

